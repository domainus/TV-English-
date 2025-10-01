#!/usr/bin/env python3
"""
TV Series M3U Playlist Generator - Fully Async aiohttp Version
Fetches TV series episodes from vixsrc.to API and creates an M3U playlist
"""

import os
import json
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict
from bs4 import BeautifulSoup, SoupStrainer
import aiohttp
from asyncio import Semaphore

# Load environment variables
load_dotenv()

class TVM3UGenerator:
    def __init__(self):
        self.api_key = os.getenv('TMDB_API_KEY')
        if not self.api_key:
            raise ValueError("TMDB_API_KEY environment variable is required")
        
        self.base_url = "https://api.themoviedb.org/3"
        self.vixsrc_api = "https://vixsrc.to/api/list/episode/?lang=it"
        self.cache_file = "serie_cache.json"
        self.cache = self._load_cache()
        self.episodes_data = self._load_vixsrc_episodes()

        # aiohttp session and concurrency control
        self.session = None
        self.semaphore = Semaphore(100)  # Limit max 100 concurrent requests

    def _load_vixsrc_episodes(self):
        """Load available episodes from vixsrc.to API"""
        try:
            print("Loading vixsrc.to episodes list...")
            import requests  # single sync call here only once
            response = requests.get(self.vixsrc_api, timeout=10)
            response.raise_for_status()
            data = response.json()
            print(f"Loaded {len(data)} episodes from vixsrc.to")
            return data
        except Exception as e:
            print(f"Warning: Could not load vixsrc.to episodes list: {e}")
            print("Continuing without vixsrc.to verification...")
            return []

    def _load_cache(self):
        """Load existing cache from file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                print(f"Loaded cache with {len(cache)} TV series")
                return cache
            except Exception as e:
                print(f"Error loading cache: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            print(f"Cache saved with {len(self.cache)} TV series")
        except Exception as e:
            print(f"Error saving cache: {e}")

    def _organize_episodes_by_series(self):
        """Organize episodes data by series ID"""
        series_episodes = defaultdict(lambda: defaultdict(list))
        for episode in self.episodes_data:
            tmdb_id = episode['tmdb_id']
            season = episode['s']
            episode_num = episode['e']
            series_episodes[tmdb_id][season].append(episode_num)
        for series_id in series_episodes:
            for season in series_episodes[series_id]:
                series_episodes[series_id][season].sort()
        return series_episodes

    async def create_session(self):
        """Create optimized aiohttp session"""
        connector = aiohttp.TCPConnector(
            limit=200,
            limit_per_host=50,
            ttl_dns_cache=300,
            force_close=False,
            enable_cleanup_closed=True
        )
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=True
        )

    async def close_session(self):
        if self.session:
            await self.session.close()

    async def _get_json(self, url, params=None):
        """Helper for JSON GET requests with semaphore"""
        async with self.semaphore:
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status != 200:
                        return None
                    return await response.json(content_type=None)
            except Exception:
                return None

    async def get_tv_genres(self):
        url = f"{self.base_url}/genre/tv/list"
        params = {'api_key': self.api_key, 'language': 'it-IT'}
        data = await self._get_json(url, params)
        if not data:
            return {}
        return {genre['id']: genre['name'] for genre in data.get('genres', [])}

    async def _fetch_series_details_async(self, tmdb_id):
        url = f"{self.base_url}/tv/{tmdb_id}"
        params = {'api_key': self.api_key, 'language': 'it-IT'}
        data = await self._get_json(url, params)
        if not data:
            return None
        # Cache partial
        cache_key = str(data['id'])
        if cache_key not in self.cache:
            self.cache[cache_key] = {
                'id': data['id'],
                'name': data['name'],
                'original_name': data.get('original_name', ''),
                'first_air_date': data.get('first_air_date', ''),
                'vote_average': data.get('vote_average', 0),
                'poster_path': data.get('poster_path', ''),
                'genre_ids': [g['id'] for g in data.get('genres', [])],
                'cached_at': datetime.now().isoformat()
            }
        return self.cache[cache_key]

    async def _get_vixsrc_m3u8_url_async(self, tmdb_id, season, episode):
        episode_page_url = f"https://vixsrc.to/tv/{tmdb_id}/{season}/{episode}"
        iframe_url = f"https://vixsrc.to/iframe/{tmdb_id}/{season}/{episode}"
        headers = {'Referer': episode_page_url}
        async with self.semaphore:
            try:
                async with self.session.get(iframe_url, headers=headers) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml", parse_only=SoupStrainer("body"))
                    script_tag = soup.find("body").find("script")
                    if script_tag and script_tag.string:
                        return self._extract_m3u8_from_script(script_tag.string)
                    return None
            except Exception:
                return None

    def _extract_m3u8_from_script(self, script_content):
        """Helper to extract m3u8 URL from embedded script"""
        token_match = re.search(r"'token':\s*'(\w+)'", script_content)
        expires_match = re.search(r"'expires':\s*'(\d+)'", script_content)
        server_url_match = re.search(r"url:\s*'([^']+)'", script_content)
        if not (token_match and expires_match and server_url_match):
            return None
        token = token_match.group(1)
        expires = expires_match.group(1)
        server_url = server_url_match.group(1)
        if "?b=1" in server_url:
            final_url = f'{server_url}&token={token}&expires={expires}'
        else:
            final_url = f"{server_url}?token={token}&expires={expires}"
        if "window.canPlayFHD = true" in script_content:
            final_url += "&h=1"
        return final_url

    async def _fetch_all_episodes_for_series(self, series, series_episodes, genres, group_title):
        tmdb_id = series['id']
        if tmdb_id not in series_episodes:
            return []
        episodes_to_fetch = []
        for season_num in sorted(series_episodes[tmdb_id].keys()):
            for episode_num in series_episodes[tmdb_id][season_num]:
                episodes_to_fetch.append((season_num, episode_num))

        tasks = [
            self._get_vixsrc_m3u8_url_async(tmdb_id, season, episode)
            for season, episode in episodes_to_fetch
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        entries = []

        # Get poster URL for tvg-logo
        poster = series.get('poster_path', '')
        tvg_logo = f"https://image.tmdb.org/t/p/w500{poster}" if poster else ""

        rating = series.get('vote_average', 0)
        stars = "★" * int(rating / 2) + "☆" * (5 - int(rating / 2)) if rating > 0 else "☆☆☆☆☆"

        for (season, episode), url in zip(episodes_to_fetch, results):
            if url and not isinstance(url, Exception):
                display_title = f"{series['name']} S{season:02d} E{episode:02d}"
                entry = (
                    f'#EXTINF:-1 type="series" tvg-logo="{tvg_logo}" group-title="SerieTV - {group_title}",'
                    f'{display_title} {stars}\n{url}\n'
                )
                entries.append((season, episode, entry))

        entries.sort()
        return [entry for _, _, entry in entries]

    async def create_complete_tv_playlist_async(self):
        await self.create_session()
        try:
            print("Creating complete TV M3U playlist asynchronously...")
            genres = await self.get_tv_genres()
            series_episodes = self._organize_episodes_by_series()
            series_ids = list(series_episodes.keys())

            print(f"Fetching details for {len(series_ids)} series from TMDB...")
            tasks = [self._fetch_series_details_async(sid) for sid in series_ids]
            series_data = await asyncio.gather(*tasks)
            series_data = [s for s in series_data if s is not None]

            # Sort series latest first by first_air_date
            def get_year(s):
                d = s.get('first_air_date', '')
                return int(d[:4]) if d and d[:4].isdigit() else 0
            series_data.sort(key=get_year, reverse=True)

            print(f"Fetching all episode URLs for each series...")
            all_entries = []
            fetch_tasks = [
                self._fetch_all_episodes_for_series(series, series_episodes, genres, "VixSrc")
                for series in series_data
            ]
            grouped_entries = await asyncio.gather(*fetch_tasks)
            for entries in grouped_entries:
                all_entries.extend(entries)

            # Write playlist
            with open("serie.m3u", 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write(f"#PLAYLIST: Serie TV VixSrc ({sum(len(v) for v in series_episodes.values())} episodi)\n\n")
                f.writelines(all_entries)

            self._save_cache()
            print(f"Complete TV playlist generated successfully: serie.m3u")
            print(f"Cache updated with {len(self.cache)} total series")
        finally:
            await self.close_session()

def main():
    try:
        generator = TVM3UGenerator()
        asyncio.run(generator.create_complete_tv_playlist_async())
        print("\nTV playlist generated successfully!")
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure to set your TMDB_API_KEY environment variable:")
        print("1. Get your API key from https://www.themoviedb.org/settings/api")
        print("2. Create a .env file with: TMDB_API_KEY=your_api_key_here")

if __name__ == "__main__":
    main()