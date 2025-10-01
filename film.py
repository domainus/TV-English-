#!/usr/bin/env python3
"""
TMDB M3U Playlist Generator - Fully Async aiohttp Version
Fetches movies from TMDB API and creates an M3U playlist with vixsrc.to links
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

class TMDBM3UGenerator:
    def __init__(self):
        self.api_key = os.getenv('TMDB_API_KEY')
        if not self.api_key:
            raise ValueError("TMDB_API_KEY environment variable is required")
        
        self.base_url = "https://api.themoviedb.org/3"
        self.vixsrc_base = "https://vixsrc.to/movie"
        self.vixsrc_api = "https://vixsrc.to/api/list/movie/?lang=it"
        self.cache_file = "film_cache.json"
        self.cache = self._load_cache()
        self.vixsrc_movies = self._load_vixsrc_movies()

        # aiohttp session and concurrency control
        self.session = None
        self.semaphore = Semaphore(100)

    def _load_vixsrc_movies(self):
        """Load available movies from vixsrc.to API (single sync call)"""
        try:
            print("Loading vixsrc.to movie list...")
            import requests
            response = requests.get(self.vixsrc_api, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            vixsrc_ids = set()
            for item in 
                if item.get('tmdb_id') and item['tmdb_id'] is not None:
                    vixsrc_ids.add(str(item['tmdb_id']))
            
            print(f"Loaded {len(vixsrc_ids)} available movies from vixsrc.to")
            return vixsrc_ids
        except Exception as e:
            print(f"Warning: Could not load vixsrc.to movie list: {e}")
            return set()

    def _load_cache(self):
        """Load existing cache from file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                print(f"Loaded cache with {len(cache)} movies")
                return cache
            except Exception as e:
                print(f"Error loading cache: {e}")
        return {}

    def _save_cache(self):
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            print(f"Cache saved with {len(self.cache)} movies")
        except Exception as e:
            print(f"Error saving cache: {e}")

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

    async def get_movie_genres(self):
        url = f"{self.base_url}/genre/movie/list"
        params = {'api_key': self.api_key, 'language': 'it-IT'}
        data = await self._get_json(url, params)
        if not 
            return {}
        return {genre['id']: genre['name'] for genre in data.get('genres', [])}

    async def get_popular_movies(self, page=1):
        url = f"{self.base_url}/movie/popular"
        params = {'api_key': self.api_key, 'page': page, 'language': 'it-IT'}
        return await self._get_json(url, params)

    async def get_latest_movies(self, page=1):
        url = f"{self.base_url}/movie/now_playing"
        params = {'api_key': self.api_key, 'page': page, 'language': 'it-IT'}
        return await self._get_json(url, params)

    async def get_top_rated_movies(self, page=1):
        url = f"{self.base_url}/movie/top_rated"
        params = {'api_key': self.api_key, 'page': page, 'language': 'it-IT'}
        return await self._get_json(url, params)

    async def _fetch_movie_details_async(self, tmdb_id):
        url = f"{self.base_url}/movie/{tmdb_id}"
        params = {'api_key': self.api_key, 'language': 'it-IT'}
        data = await self._get_json(url, params)
        if not 
            return None
        
        # Cache the result
        cache_key = str(data['id'])
        if cache_key not in self.cache:
            self.cache[cache_key] = {
                'id': data['id'],
                'title': data['title'],
                'release_date': data.get('release_date', ''),
                'vote_average': data.get('vote_average', 0),
                'poster_path': data.get('poster_path', ''),
                'genre_ids': [g['id'] for g in data.get('genres', [])],
                'cached_at': datetime.now().isoformat()
            }
        return self.cache[cache_key]

    async def _get_vixsrc_m3u8_url_async(self, tmdb_id):
        """Extract direct .m3u8 URL from vixsrc.to page."""
        movie_page_url = f"{self.vixsrc_base}/{tmdb_id}/?lang=it"
        async with self.semaphore:
            try:
                async with self.session.get(movie_page_url) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
                    
                    soup = BeautifulSoup(html, "lxml", parse_only=SoupStrainer("body"))
                    body_tag = soup.find("body")
                    if not body_tag:
                        return None
                    script_tag = body_tag.find("script")
                    if not script_tag or not script_tag.string:
                        return None

                    script_content = script_tag.string
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
            except Exception:
                return None

    async def _fetch_movie_with_url(self, movie, genres, group_title):
        """Fetch m3u8 URL for a movie and return the M3U entry string."""
        tmdb_id = movie['id']
        url = await self._get_vixsrc_m3u8_url_async(tmdb_id)
        
        if not url:
            return None
        
        title = movie['title']
        year = movie.get('release_date', '')[:4] if movie.get('release_date') else ''
        rating = movie.get('vote_average', 0)
        stars = "★" * int(rating / 2) + "☆" * (5 - int(rating / 2)) if rating > 0 else "☆☆☆☆☆"
        
        poster_path = movie.get('poster_path', '')
        tvg_logo = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        
        display_title = f"{title} ({year}) {stars}"
        
        return f'#EXTINF:-1 type="movie" tvg-logo="{tvg_logo}" group-title="Film - {group_title}",{display_title}\n{url}\n'

    async def _fetch_section_entries_async(self, movies, genres, group_title):
        """Fetch all movie URLs for a section in parallel."""
        if not movies:
            return []
        
        print(f"   Fetching '{group_title}' section ({len(movies)} movies)...")
        
        tasks = [
            self._fetch_movie_with_url(movie, genres, group_title)
            for movie in movies
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        section_entries = [f"\n# {group_title}\n"]
        added_count = 0
        for result in results:
            if result and not isinstance(result, Exception):
                section_entries.append(result)
                added_count += 1
        
        print(f"      Added {added_count} movies to {group_title}")
        return section_entries

    async def create_complete_playlist_async(self):
        await self.create_session()
        
        try:
            print("Creating complete M3U playlist asynchronously...")
            genres = await self.get_movie_genres()
            
            print(f"\nFetching movie details for {len(self.vixsrc_movies)} available movies...")
            
            # Fetch movie details in parallel
            tasks = [self._fetch_movie_details_async(tmdb_id) for tmdb_id in self.vixsrc_movies]
            movies_data = await asyncio.gather(*tasks)
            movies_data = [m for m in movies_data if m is not None]
            
            print(f"Successfully loaded {len(movies_data)} movie details")
            
            # Fetch category data
            print("Fetching real category data from TMDB...")
            
            # Fetch popular movies (3 pages)
            popular_tasks = [self.get_popular_movies(page=p) for p in range(1, 4)]
            popular_results = await asyncio.gather(*popular_tasks)
            popular_ids = set()
            for result in popular_results:
                if result:
                    for movie in result.get('results', []):
                        popular_ids.add(str(movie['id']))
            
            # Fetch now playing movies (2 pages)
            cinema_tasks = [self.get_latest_movies(page=p) for p in range(1, 3)]
            cinema_results = await asyncio.gather(*cinema_tasks)
            cinema_ids = set()
            for result in cinema_results:
                if result:
                    for movie in result.get('results', []):
                        cinema_ids.add(str(movie['id']))
            
            # Fetch top rated movies (2 pages)
            top_rated_tasks = [self.get_top_rated_movies(page=p) for p in range(1, 3)]
            top_rated_results = await asyncio.gather(*top_rated_tasks)
            top_rated_ids = set()
            for result in top_rated_results:
                if result:
                    for movie in result.get('results', []):
                        top_rated_ids.add(str(movie['id']))
            
            # Group movies by categories
            cinema_movies = []
            popular_movies = []
            top_rated_movies = []
            genre_movies = defaultdict(list)
            
            for movie in movies_
                movie_id = str(movie['id'])
                
                if movie_id in cinema_ids:
                    cinema_movies.append(movie)
                if movie_id in popular_ids:
                    popular_movies.append(movie)
                if movie_id in top_rated_ids:
                    top_rated_movies.append(movie)
                
                for genre_id in movie['genre_ids']:
                    genre_name = genres.get(genre_id)
                    if genre_name:
                        genre_movies[genre_name].append(movie)
            
            # Fetch all entries in parallel
            print("\nFetching all movie URLs...")
            
            all_entries = []
            
            # 1. Cinema movies (limit 50)
            print("\n1. Adding 'Film Al Cinema' section...")
            entries = await self._fetch_section_entries_async(cinema_movies[:50], genres, "Al Cinema")
            all_entries.extend(entries)
            
            # 2. Popular movies (limit 50)
            print("\n2. Adding 'Popolari' section...")
            entries = await self._fetch_section_entries_async(popular_movies[:50], genres, "Popolari")
            all_entries.extend(entries)
            
            # 3. Top rated movies (limit 50)
            print("\n3. Adding 'Più Votati' section...")
            entries = await self._fetch_section_entries_async(top_rated_movies[:50], genres, "Più Votati")
            all_entries.extend(entries)
            
            # 4. Genres
            print("\n4. Adding genre-specific sections...")
            for genre_name, movies in genre_movies.items():
                if movies:
                    movies_sorted = sorted(
                        movies,
                        key=lambda m: m.get('release_date', ''),
                        reverse=True
                    )
                    entries = await self._fetch_section_entries_async(movies_sorted, genres, genre_name)
                    all_entries.extend(entries)
            
            # Write playlist
            with open("film.m3u", 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write(f"#PLAYLIST:Film VixSrc ({len(movies_data)} Film)\n")
                f.writelines(all_entries)
            
            self._save_cache()
            print(f"\nComplete playlist generated successfully: film.m3u")
            print(f"Cache updated with {len(self.cache)} total movies")
            
        finally:
            await self.close_session()

def main():
    try:
        generator = TMDBM3UGenerator()
        asyncio.run(generator.create_complete_playlist_async())
        print("\nPlaylist generated successfully!")
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure to set your TMDB_API_KEY environment variable:")
        print("1. Get your API key from https://www.themoviedb.org/settings/api")
        print("2. Create a .env file with: TMDB_API_KEY=your_api_key_here")

if __name__ == "__main__":
    main()
