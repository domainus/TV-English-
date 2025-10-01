#!/usr/bin/env python3
"""
TV Series M3U Playlist Generator
Fetches TV series episodes from vixsrc.to API and creates an M3U playlist
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json
import hashlib
import re
from bs4 import BeautifulSoup, SoupStrainer
from tqdm import tqdm
from collections import defaultdict

# Load environment variables
load_dotenv()

class TVM3UGenerator:
    def __init__(self):
        self.api_key = os.getenv('TMDB_API_KEY')
        self.base_url = "https://api.themoviedb.org/3"
        self.vixsrc_base = "https://vixsrc.to/tv"
        self.vixsrc_api = "https://vixsrc.to/api/list/episode/?lang=it"
        self.cache_file = "serie_cache.json"
        self.cache = self._load_cache()
        self.episodes_data = self._load_vixsrc_episodes()
        
        if not self.api_key:
            raise ValueError("TMDB_API_KEY environment variable is required")
    
    def _load_vixsrc_episodes(self):
        """Load available episodes from vixsrc.to API"""
        try:
            print("Loading vixsrc.to episodes list...")
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
    
    def _get_cache_key(self, series):
        """Generate cache key for a TV series"""
        return str(series['id'])
    
    def _is_series_cached(self, series):
        """Check if series is already in cache"""
        cache_key = self._get_cache_key(series)
        return cache_key in self.cache
    
    def _add_to_cache(self, series):
        """Add series to cache"""
        cache_key = self._get_cache_key(series)
        self.cache[cache_key] = {
            'id': series['id'],
            'name': series['name'],
            'original_name': series.get('original_name', ''),
            'first_air_date': series.get('first_air_date', ''),
            'vote_average': series.get('vote_average', 0),
            'poster_path': series.get('poster_path', ''),
            'genre_ids': series.get('genre_ids', []),
            'cached_at': datetime.now().isoformat()
        }
    
    def get_popular_tv(self, page=1, language='it-IT'):
        """Fetch popular TV series from TMDB"""
        url = f"{self.base_url}/tv/popular"
        params = {
            'api_key': self.api_key,
            'page': page,
            'language': language
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_top_rated_tv(self, page=1, language='it-IT'):
        """Fetch top rated TV series from TMDB"""
        url = f"{self.base_url}/tv/top_rated"
        params = {
            'api_key': self.api_key,
            'page': page,
            'language': language
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_on_air_tv(self, page=1, language='it-IT'):
        """Fetch currently on air TV series from TMDB"""
        url = f"{self.base_url}/tv/on_the_air"
        params = {
            'api_key': self.api_key,
            'page': page,
            'language': language
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_tv_genres(self):
        """Fetch TV genres from TMDB"""
        url = f"{self.base_url}/genre/tv/list"
        params = {
            'api_key': self.api_key,
            'language': 'it-IT'
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        return {genre['id']: genre['name'] for genre in response.json()['genres']}
    
    def _fetch_series_details(self, tmdb_id):
        """Fetch TV series details from TMDB by ID"""
        url = f"{self.base_url}/tv/{tmdb_id}"
        params = {
            'api_key': self.api_key,
            'language': 'it-IT'
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            series_data = response.json()
            
            # Convert to the format expected by the rest of the code
            return {
                'id': series_data['id'],
                'name': series_data['name'],
                'original_name': series_data.get('original_name', ''),
                'first_air_date': series_data.get('first_air_date', ''),
                'vote_average': series_data.get('vote_average', 0),
                'poster_path': series_data.get('poster_path', ''),
                'genre_ids': [genre['id'] for genre in series_data.get('genres', [])]
            }
        except Exception as e:
            # Sanitize the error message to remove the API key
            error_message = str(e).replace(self.api_key, '***')
            print(f"      Error fetching series {tmdb_id}: {error_message}")
            return None
    
    def _organize_episodes_by_series(self):
        """Organize episodes data by series ID"""
        series_episodes = defaultdict(lambda: defaultdict(list))
        
        for episode in self.episodes_data:
            tmdb_id = episode['tmdb_id']
            season = episode['s']
            episode_num = episode['e']
            
            series_episodes[tmdb_id][season].append(episode_num)
        
        # Sort episodes within each season
        for series_id in series_episodes:
            for season in series_episodes[series_id]:
                series_episodes[series_id][season].sort()
        
        return series_episodes
    
    def create_complete_tv_playlist(self):
        """Create one complete M3U file with all TV series and episodes"""
        print("Creating complete TV M3U playlist from vixsrc.to episodes...")
        
        # Get genres mapping
        genres = self.get_tv_genres()
        
        # Organize episodes by series
        series_episodes = self._organize_episodes_by_series()
        
        # Get unique series IDs
        series_ids = list(series_episodes.keys())
        print(f"Found {len(series_ids)} unique TV series with episodes")
        
        # Fetch series details from TMDB
        print(f"\nFetching series details for {len(series_ids)} series...")
        series_data = self._get_series_from_vixsrc_list(series_ids)

        # Sort series by first_air_date (newest first), handling missing/invalid dates
        def parse_year(s):
            date = s.get('first_air_date', '')
            try:
                return int(date[:4]) if date and date[:4].isdigit() else 0
            except Exception:
                return 0
        series_data = sorted(
            series_data,
            key=parse_year,
            reverse=True
        )
        
        # Count total episodes
        total_episodes = sum(len(episodes) for series in series_episodes.values() 
                           for episodes in series.values())
        
        # 1. Build all playlist parts in memory
        playlist_parts = []
        playlist_parts.append("#EXTM3U\n")
        playlist_parts.append(f"#PLAYLIST:Serie TV VixSrc ({total_episodes} Episodi)\n")

        # 2. Organize series and get all entry strings
        series_entries = self._organize_and_get_series_entries(series_data, series_episodes, genres)
        playlist_parts.extend(series_entries)
        
        # 3. Write the complete playlist to the file at once
        with open("serie.m3u", 'w', encoding='utf-8') as f:
            f.write("".join(playlist_parts))
        
        self._save_cache()
        print(f"\nComplete TV playlist generated successfully: serie.m3u")
        print(f"Cache updated with {len(self.cache)} total series")
    
    def _get_series_from_vixsrc_list(self, series_ids):
        """Fetch series details for all series available on vixsrc.to, using cache when possible"""
        series_data = []
        total_series = len(series_ids)
        
        print(f"Fetching details for {total_series} series from TMDB (using cache)...")
        
        # Prepare list of tmdb_ids to fetch (not in cache)
        to_fetch = []
        for tmdb_id in series_ids:
            if str(tmdb_id) in self.cache:
                # Use cached data
                series_data.append(self.cache[str(tmdb_id)])
            else:
                to_fetch.append(tmdb_id)
        
        print(f"{len(series_data)} series loaded from cache, {len(to_fetch)} to fetch from TMDB...")
        
        # Use ThreadPoolExecutor to fetch series details in parallel
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_tmdb_id = {
                executor.submit(self._fetch_series_details, tmdb_id): tmdb_id 
                for tmdb_id in to_fetch
            }
            completed = 0
            for future in as_completed(future_to_tmdb_id):
                tmdb_id = future_to_tmdb_id[future]
                try:
                    series_detail = future.result()
                    if series_detail:
                        series_data.append(series_detail)
                        # Add to cache
                        if not self._is_series_cached(series_detail):
                            self._add_to_cache(series_detail)
                    completed += 1
                    if completed % 50 == 0:
                        print(f"   Completed {completed}/{len(to_fetch)} TMDB requests...")
                except Exception as e:
                    # Sanitize the error message to remove the API key
                    error_message = str(e).replace(self.api_key, '***')
                    print(f"   Error fetching series {tmdb_id}: {error_message}")
        
        print(f"Successfully loaded {len(series_data)} series details (cache+TMDB)")
        return series_data
    
    def _organize_and_get_series_entries(self, series_data, series_episodes, genres):
        """Organize series by categories and return a list of M3U entry strings."""
        all_entries = []
        # Get real category data from TMDB
        print("Fetching real category data from TMDB...")
        
        # Get popular series (real data)
        popular_ids = set()
        for page in range(1, 4):  # 3 pages for popular
            try:
                popular_data = self.get_popular_tv(page=page)
                for series in popular_data['results']:
                    popular_ids.add(str(series['id']))
            except Exception as e:
                # Sanitize the error message to remove the API key
                error_message = str(e).replace(self.api_key, '***')
                print(f"Error fetching popular series page {page}: {error_message}")
        
        # Get on air series (real data)
        on_air_ids = set()
        for page in range(1, 3):  # 2 pages for on air
            try:
                on_air_data = self.get_on_air_tv(page=page)
                for series in on_air_data['results']:
                    on_air_ids.add(str(series['id']))
            except Exception as e:
                # Sanitize the error message to remove the API key
                error_message = str(e).replace(self.api_key, '***')
                print(f"Error fetching on air series page {page}: {error_message}")
        
        # Get top rated series (real data)
        top_rated_ids = set()
        for page in range(1, 3):  # 2 pages for top rated
            try:
                top_rated_data = self.get_top_rated_tv(page=page)
                for series in top_rated_data['results']:
                    top_rated_ids.add(str(series['id']))
            except Exception as e:
                # Sanitize the error message to remove the API key
                error_message = str(e).replace(self.api_key, '***')
                print(f"Error fetching top rated series page {page}: {error_message}")
        
        # Group series by real categories
        on_air_series = []
        popular_series = []
        top_rated_series = []
        genre_series = {genre_name: [] for genre_name in genres.values()}
        
        # Create a mapping of series_id to series_data
        series_map = {str(series['id']): series for series in series_data}
        
        # Process all series
        for series in series_data:
            series_id = str(series['id'])
            
            # Add to appropriate categories based on real TMDB data
            if series_id in on_air_ids:
                on_air_series.append(series)
            if series_id in popular_ids:
                popular_series.append(series)
            if series_id in top_rated_ids:
                top_rated_series.append(series)
            
            # Add to genre categories
            for genre_id in series['genre_ids']:
                genre_name = genres.get(genre_id)
                if genre_name:
                    genre_series[genre_name].append(series)
        
        # 1. Serie in Onda (limit 30)
        print("\n1. Adding 'Serie in Onda' section...")
        all_entries.extend(self._fetch_section_entries_parallel(on_air_series[:30], series_episodes, genres, "Serie in Onda"))
        
        # 2. Popolari (limit 30)
        print("\n2. Adding 'Popolari' section...")
        all_entries.extend(self._fetch_section_entries_parallel(popular_series[:30], series_episodes, genres, "Popolari"))
        
        # 3. Più Votate (limit 30)
        print("\n3. Adding 'Più Votate' section...")
        all_entries.extend(self._fetch_section_entries_parallel(top_rated_series[:30], series_episodes, genres, "Più Votate"))
        
        # 4. Genres
        print("\n4. Adding genre-specific sections...")
        for genre_name, series_list in genre_series.items():
            if series_list:  # Only add genres that have series
                # Sort series by first air date (newest first)
                series_sorted = sorted(
                    series_list,
                    key=lambda s: s.get('first_air_date', ''),
                    reverse=True
                )
                all_entries.extend(self._fetch_section_entries_parallel(series_sorted, series_episodes, genres, genre_name))
        
        return all_entries

    def _get_series_episodes_entries(self, series, series_episodes, genres, group_title):
        """
        Fetches all episode URLs for a single series in parallel and 
        returns a list of M3U entry strings for that series.
        """
        tmdb_id = series['id']
        
        # Check if series has episodes
        if tmdb_id not in series_episodes:
            return []
        
        series_name = series['name']
        year = series.get('first_air_date', '')[:4] if series.get('first_air_date') else ''
        
        # Get rating and create stars
        rating = series.get('vote_average', 0)
        stars = "★" * int(rating / 2) + "☆" * (5 - int(rating / 2)) if rating > 0 else "☆☆☆☆☆"
        
        # Get all genres
        genre_names = []
        if series.get('genre_ids') and series['genre_ids']:
            for genre_id in series['genre_ids']:
                genre_name = genres.get(genre_id, "")
                if genre_name:
                    genre_names.append(genre_name)
        
        # Get poster URL
        poster_path = series.get('poster_path', '')
        tvg_logo = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        
        # Prepare a list of all episodes to fetch for this series
        episodes_to_fetch = []
        for season_num in sorted(series_episodes[tmdb_id].keys()):
            for episode_num in series_episodes[tmdb_id][season_num]:
                episodes_to_fetch.append((season_num, episode_num))

        series_entries = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_episode = {
                executor.submit(self._get_vixsrc_m3u8_url, tmdb_id, s, e): (s, e)
                for s, e in episodes_to_fetch
            }

            progress_bar = tqdm(as_completed(future_to_episode), total=len(episodes_to_fetch), desc=f"   - {series_name}", leave=False, unit=" ep")

            for future in progress_bar:
                season_num, episode_num = future_to_episode[future]
                episode_url = future.result()

                if episode_url:
                    display_title = f"{series_name} S{season_num:02d} E{episode_num:02d}"
                    entry_string = f'#EXTINF:-1 type="series" tvg-logo="{tvg_logo}" group-title="SerieTV - {group_title}",{display_title}\n{episode_url}\n'
                    series_entries.append((season_num, episode_num, entry_string))

        # Sort entries by season and episode number before returning
        series_entries.sort()
        return [entry for _, _, entry in series_entries]

    def _fetch_section_entries_parallel(self, series_list, series_episodes, genres, group_title):
        """Fetches all M3U entries for a list of series and returns them."""
        if not series_list:
            return []

        section_entries = []
        section_entries.append(f"\n# {group_title}\n")
        
        print(f"   Adding '{group_title}' section ({len(series_list)} series)...")
        
        added_count = 0
        for series in series_list:
            entries = self._get_series_episodes_entries(series, series_episodes, genres, group_title)
            if entries:
                section_entries.extend(entries)
                added_count += 1
        
        print(f"      Added {added_count} series to {group_title}")
        return section_entries

    def _get_vixsrc_m3u8_url(self, tmdb_id, season, episode):
        """Extract direct .m3u8 URL from a vixsrc.to episode page."""
        episode_page_url = f"https://vixsrc.to/tv/{tmdb_id}/{season}/{episode}"
        try:
            # The URL for the actual player iframe is different
            iframe_url = f"https://vixsrc.to/iframe/{tmdb_id}/{season}/{episode}"
            
            # Vixsrc requires a 'Referer' header pointing to the episode page
            headers = {'Referer': episode_page_url}
            
            response = requests.get(iframe_url, headers=headers, timeout=10)
            response.raise_for_status()

            # The logic is similar to film.py: find the script tag in the body
            soup = BeautifulSoup(response.text, "lxml", parse_only=SoupStrainer("body"))
            script_tag = soup.find("body").find("script")
            if not script_tag or not script_tag.string:
                # Fallback for a different structure if the first fails
                iframe_src_match = re.search(r'iframe\s+src="([^"]+)"', response.text)
                if iframe_src_match:
                    # Sometimes there's another layer of iframe
                    nested_iframe_url = iframe_src_match.group(1)
                    return self._extract_m3u8_from_final_page(nested_iframe_url, iframe_url)
                return None

            return self._extract_m3u8_from_script(script_tag.string)

        except Exception:
            # Errors are frequent, so we suppress the output to avoid noise.
            # The function will return None, and the episode will be skipped.
            return None

    def _extract_m3u8_from_script(self, script_content):
        """Helper to extract m3u8 from script content."""
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

def main():
    """Main function to run the TV generator"""
    try:
        generator = TVM3UGenerator()
        
        print("TV Series M3U Playlist Generator")
        print("=" * 40)
        
        # Create complete TV playlist
        generator.create_complete_tv_playlist()
        
        print("\nTV playlist generated successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure to set your TMDB_API_KEY environment variable:")
        print("1. Get your API key from https://www.themoviedb.org/settings/api")
        print("2. Create a .env file with: TMDB_API_KEY=your_api_key_here")

if __name__ == "__main__":
    main() 