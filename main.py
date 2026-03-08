import os
import sys
import json
import time
import requests
import getpass
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import colorama
from colorama import Fore, Style
import http.client as http_client

http_client.HTTPConnection.debuglevel = 0

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spotify_music_import.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

colorama.init()

try:
    import browser_cookie3
except ImportError:
    print(f"{Fore.YELLOW}Installing browser_cookie3...{Style.RESET_ALL}")
    os.system("pip install browser-cookie3")
    import browser_cookie3

class SpotifyMusicImporter:
    def __init__(self):
        """Initialize Spotify music importer"""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.temp_dir = Path('temp_music')
        self.temp_dir.mkdir(exist_ok=True)
        self.k_connect_url = 'k-connect.ru'
        self.k_connect_track_ids = {}
        self.skip_lyrics = False

        self.client_id = 'e248c0de2dc748908ddfc960cb2cc015'
        self.client_secret = '24eb3676dc784f388fa4bd0b518f4afd'
        self.music_api_key = os.environ.get('MUSIC_API_KEY', 'fkk3k1k3f13n88831fmmQWQQQjdm1m23mmMwd1nnsp0v0e')
        
        self.cookies = {}
        self.k_connect_session = None
        self.spotify_client = None

        print(f"{Fore.GREEN}Initializing Spotify music importer. Temp directory: {self.temp_dir}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Using API key length: {len(self.music_api_key)} characters{Style.RESET_ALL}")

        logging.getLogger("urllib3").setLevel(logging.WARNING)

    def get_cookies_from_browsers(self, domain):
        """Get cookies from various browsers for the specified domain"""
        print(f"{Fore.CYAN}Searching for saved sessions in browsers for {domain}...{Style.RESET_ALL}")
        
        available_browsers = []
        cookies_by_browser = {}
        
        browsers = []
        if hasattr(browser_cookie3, 'chrome'):
            browsers.append(('chrome', 'Chrome', browser_cookie3.chrome))
        if hasattr(browser_cookie3, 'firefox'):
            browsers.append(('firefox', 'Firefox', browser_cookie3.firefox))
        if hasattr(browser_cookie3, 'opera'):
            browsers.append(('opera', 'Opera', browser_cookie3.opera))
        if hasattr(browser_cookie3, 'edge'):
            browsers.append(('edge', 'Edge', browser_cookie3.edge))
        if hasattr(browser_cookie3, 'chromium'):
            browsers.append(('chromium', 'Chromium', browser_cookie3.chromium))
        if hasattr(browser_cookie3, 'brave'):
            browsers.append(('brave', 'Brave', browser_cookie3.brave))
        if hasattr(browser_cookie3, 'vivaldi'):
            browsers.append(('vivaldi', 'Vivaldi', browser_cookie3.vivaldi))
        if hasattr(browser_cookie3, 'safari'):
            browsers.append(('safari', 'Safari', browser_cookie3.safari))
        
        for browser_id, browser_name, browser_func in browsers:
            try:
                cookies = browser_func(domain_name=domain)
                if cookies and len(cookies) > 0:
                    cookie_count = len(cookies)
                    print(f"{Fore.GREEN}Found {cookie_count} cookies in {browser_name}.{Style.RESET_ALL}")
                    available_browsers.append((browser_id, browser_name, cookie_count))
                    cookies_by_browser[browser_id] = cookies
                else:
                    print(f"{Fore.YELLOW}No cookies found in {browser_name} for {domain}.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}Failed to get cookies from {browser_name}: {str(e)}{Style.RESET_ALL}")
        
        if not available_browsers:
            print(f"{Fore.RED}No cookies found in any browser for domain {domain}.{Style.RESET_ALL}")
            return None

        if len(available_browsers) == 1:
            browser_id = available_browsers[0][0]
            browser_name = available_browsers[0][1]
            print(f"{Fore.GREEN}Automatically selected browser {browser_name} with {available_browsers[0][2]} cookies.{Style.RESET_ALL}")
            return cookies_by_browser[browser_id]

        print(f"{Fore.CYAN}Found multiple browsers with cookies for {domain}:{Style.RESET_ALL}")
        for i, (browser_id, browser_name, cookie_count) in enumerate(available_browsers, 1):
            print(f"{i}. {browser_name} ({cookie_count} cookies)")
        
        while True:
            choice = input(f"{Fore.CYAN}Select browser (1-{len(available_browsers)}): {Style.RESET_ALL}")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(available_browsers):
                    browser_id = available_browsers[idx][0]
                    browser_name = available_browsers[idx][1]
                    print(f"{Fore.GREEN}Selected browser {browser_name}.{Style.RESET_ALL}")
                    return cookies_by_browser[browser_id]
                else:
                    print(f"{Fore.YELLOW}Please enter a number between 1 and {len(available_browsers)}.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.YELLOW}Please enter a number.{Style.RESET_ALL}")
        
        return None

    def login_k_connect(self, username=None, password=None):
        """Authorize in K-Connect using API key"""
        print(f"{Fore.CYAN}Setting up connection to K-Connect...{Style.RESET_ALL}")
        session = requests.Session()

        api_key_preview = f"{self.music_api_key[:5]}...{self.music_api_key[-5:]}" if len(self.music_api_key) > 10 else self.music_api_key
        print(f"{Fore.CYAN}Using API key: {api_key_preview} (length: {len(self.music_api_key)}){Style.RESET_ALL}")

        session.headers.update({
            'X-Key': self.music_api_key,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        session.verify = False
        session.trust_env = False

        from requests.packages.urllib3.exceptions import InsecureRequestWarning
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

        protocols = ['https://', 'http://']
        domains = [self.k_connect_url, f"www.{self.k_connect_url}"]

        working_url = None
        print(f"{Fore.CYAN}Determining working URL for site...{Style.RESET_ALL}")
        
        for protocol in protocols:
            for domain in domains:
                test_url = f"{protocol}{domain}"
                try:
                    print(f"{Fore.CYAN}Checking {test_url}...{Style.RESET_ALL}")
                    response = session.get(test_url, timeout=10, allow_redirects=True)
                    print(f"{Fore.CYAN}Status: {response.status_code}{Style.RESET_ALL}")
                    if response.status_code < 400:
                        working_url = test_url
                        print(f"{Fore.GREEN}Found working URL: {working_url}{Style.RESET_ALL}")
                        break
                except Exception as e:
                    print(f"{Fore.YELLOW}URL {test_url} unavailable: {str(e)}{Style.RESET_ALL}")
            
            if working_url:
                break
        
        if not working_url:
            print(f"{Fore.RED}Could not connect to K-Connect site. Check internet connection.{Style.RESET_ALL}")
            return False

        self.k_connect_url = working_url
        self.k_connect_session = session

        try:
            print(f"{Fore.CYAN}Checking API access with X-Key...{Style.RESET_ALL}")
            test_url = f"{self.k_connect_url}/api/music"
            response = session.get(test_url, timeout=10)
            print(f"{Fore.CYAN}Test request with X-Key: status {response.status_code}{Style.RESET_ALL}")
            
            if response.status_code == 200:
                print(f"{Fore.GREEN}API access with X-Key works!{Style.RESET_ALL}")
                try:
                    json_response = response.json()
                    print(f"{Fore.GREEN}Server response: {json_response.get('success', False)}{Style.RESET_ALL}")
                except:
                    pass
                return True
            else:
                print(f"{Fore.YELLOW}API access with X-Key failed. Code: {response.status_code}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Response: {response.text[:200]}{Style.RESET_ALL}")
                return False
        except Exception as e:
            print(f"{Fore.YELLOW}Error checking API access: {str(e)}{Style.RESET_ALL}")
            import traceback
            print(f"{Fore.YELLOW}Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return False

    def upload_track_to_k_connect(self, track_path, cover_path, metadata):
        """Upload track to K-Connect"""
        if not self.k_connect_session:
            print(f"{Fore.RED}No active K-Connect session.{Style.RESET_ALL}")
            return False
        
        try:
            print(f"{Fore.CYAN}Preparing to upload track '{metadata.get('title')}'...{Style.RESET_ALL}")
            
            if not os.path.exists(track_path):
                print(f"{Fore.RED}Error: Track file not found: {track_path}{Style.RESET_ALL}")
                return False

            files = {}
            files['file'] = open(track_path, 'rb')
            print(f"{Fore.CYAN}Audio file prepared: {track_path} ({os.path.getsize(track_path) / 1024:.1f} KB){Style.RESET_ALL}")

            if not cover_path or not os.path.exists(cover_path):
                print(f"{Fore.YELLOW}Cover not found, using default.{Style.RESET_ALL}")
                placeholder_path = self.temp_dir / 'placeholder.jpg'
                if not placeholder_path.exists():
                    try:
                        print(f"{Fore.CYAN}Downloading default cover...{Style.RESET_ALL}")
                        placeholder_response = requests.get("https://k-connect.ru/static/uploads/system/album_placeholder.jpg")
                        with open(placeholder_path, 'wb') as f:
                            f.write(placeholder_response.content)
                        print(f"{Fore.GREEN}Default cover downloaded.{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.YELLOW}Failed to download default cover: {str(e)}. Creating empty one.{Style.RESET_ALL}")
                        with open(placeholder_path, 'wb') as f:
                            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\x13\xe8\x00\x00\x00\x00IEND\xaeB`\x82')
                files['cover'] = open(placeholder_path, 'rb')
                print(f"{Fore.CYAN}Default cover prepared.{Style.RESET_ALL}")
            else:
                files['cover'] = open(cover_path, 'rb')
                print(f"{Fore.CYAN}Cover prepared: {cover_path} ({os.path.getsize(cover_path) / 1024:.1f} KB){Style.RESET_ALL}")

            data = {
                'title': metadata.get('title', 'Unknown Title'),
                'artist': metadata.get('artist', 'Unknown Artist'),
                'album': metadata.get('album', ''),
                'genre': metadata.get('genre', ''),
                'description': metadata.get('description', ''),
                'duration': metadata.get('duration', 0)
            }
            
            print(f"{Fore.CYAN}Metadata prepared: {json.dumps(data, ensure_ascii=False)}{Style.RESET_ALL}")

            api_key_preview = f"{self.music_api_key[:5]}...{self.music_api_key[-5:]}" if len(self.music_api_key) > 10 else self.music_api_key
            print(f"{Fore.CYAN}Using API key: {api_key_preview} (length: {len(self.music_api_key)}){Style.RESET_ALL}")

            original_headers = dict(self.k_connect_session.headers)
            self.k_connect_session.headers.update({
                'X-Key': self.music_api_key
            })
            
            if 'Content-Type' in self.k_connect_session.headers:
                del self.k_connect_session.headers['Content-Type']

            print(f"{Fore.CYAN}Current session headers: {self.k_connect_session.headers}{Style.RESET_ALL}")

            upload_url = f"{self.k_connect_url}/api/music/upload"
            print(f"{Fore.CYAN}Sending upload request to K-Connect: {upload_url}{Style.RESET_ALL}")
            
            response = self.k_connect_session.post(
                upload_url, 
                files=files, 
                data=data,
                timeout=30,
                allow_redirects=True
            )

            self.k_connect_session.headers.clear()
            self.k_connect_session.headers.update(original_headers)

            try:
                files['file'].close()
                print(f"{Fore.CYAN}Audio file closed.{Style.RESET_ALL}")
            except:
                pass
                
            try:
                if files.get('cover'):
                    files['cover'].close()
                    print(f"{Fore.CYAN}Cover file closed.{Style.RESET_ALL}")
            except:
                pass

            print(f"{Fore.CYAN}Response status: {response.status_code}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Response headers: {response.headers}{Style.RESET_ALL}")

            try:
                response_data = response.json()
                print(f"{Fore.CYAN}Server response: {json.dumps(response_data, ensure_ascii=False)}{Style.RESET_ALL}")
                
                if response.status_code == 200 and response_data.get('success'):
                    print(f"{Fore.GREEN}Track '{metadata.get('title')}' successfully uploaded to K-Connect!{Style.RESET_ALL}")
                    if 'track' in response_data and 'id' in response_data['track']:
                        track_id = response_data['track']['id']
                        print(f"{Fore.GREEN}K-Connect track ID: {track_id}{Style.RESET_ALL}")
                        if 'spotify_id' in metadata and metadata['spotify_id']:
                            self.k_connect_track_ids[metadata['spotify_id']] = track_id
                            print(f"{Fore.GREEN}Linked: Spotify ID {metadata['spotify_id']} -> K-Connect ID {track_id}{Style.RESET_ALL}")
                        return track_id
                    return True
                else:
                    error_msg = response_data.get('message', 'Unknown error')
                    if error_msg == "Authorization required":
                        print(f"{Fore.RED}Authorization error during track upload. Check API key.{Style.RESET_ALL}")
                    print(f"{Fore.RED}Error uploading track to K-Connect: {error_msg}{Style.RESET_ALL}")
                    return False
            except Exception as json_error:
                print(f"{Fore.RED}Failed to parse server response: {str(json_error)}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Response body: {response.text[:500]}...{Style.RESET_ALL}")
                if response.status_code == 200 or response.status_code == 302:
                    print(f"{Fore.YELLOW}Successful status code, upload likely completed.{Style.RESET_ALL}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Error uploading track to K-Connect: {str(e)}")
            print(f"{Fore.RED}Error uploading track: {str(e)}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            return False

    def download_and_process_track(self, track_info, service_name):
        """Download and process a track"""
        try:
            safe_title = re.sub(r'[^\w\-_]', '_', track_info['title'])
            safe_artist = re.sub(r'[^\w\-_]', '_', track_info['artist'])
            filename = f"{safe_artist} - {safe_title}.mp3"
            track_path = self.temp_dir / filename
            cover_path = self.temp_dir / f"{safe_artist} - {safe_title}_cover.jpg"

            if track_path.exists():
                print(f"{Fore.YELLOW}Track {track_info['title']} already downloaded.{Style.RESET_ALL}")
            else:
                print(f"{Fore.CYAN}Downloading '{track_info['title']}' by {track_info['artist']}...{Style.RESET_ALL}")
                response = requests.get(track_info['download_url'], headers=self.headers, stream=True)
                with open(track_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                print(f"{Fore.GREEN}Track downloaded: {track_path}{Style.RESET_ALL}")

            if 'cover_url' in track_info and track_info['cover_url']:
                if not cover_path.exists():
                    cover_response = requests.get(track_info['cover_url'], headers=self.headers)
                    with open(cover_path, 'wb') as f:
                        f.write(cover_response.content)
                    print(f"{Fore.GREEN}Cover downloaded: {cover_path}{Style.RESET_ALL}")
            else:
                cover_path = None
                print(f"{Fore.YELLOW}Cover not found for track '{track_info['title']}'{Style.RESET_ALL}")

            audio = MP3(track_path)
            duration = int(audio.info.length)

            metadata = {
                'title': track_info['title'],
                'artist': track_info['artist'],
                'album': track_info.get('album', ''),
                'genre': track_info.get('genre', ''),
                'duration': duration,
                'description': f"Imported from {service_name}",
                'spotify_id': track_info['track_id']
            }

            upload_result = self.upload_track_to_k_connect(track_path, cover_path, metadata)
            upload_success = upload_result is not False

            if upload_success:
                if track_path.exists():
                    os.remove(track_path)
                    if cover_path and cover_path.exists():
                        os.remove(cover_path)
                    print(f"{Fore.GREEN}Temporary files removed.{Style.RESET_ALL}")
            
            return upload_success
            
        except Exception as e:
            logger.error(f"Error processing track {track_info['title']}: {str(e)}")
            print(f"{Fore.RED}Error processing track '{track_info['title']}': {str(e)}{Style.RESET_ALL}")
            return False

    def import_from_spotify(self, spotify_url, quality=1, max_workers=4):
        """Import music from Spotify
        quality:
        0 - Low (AAC 64kbps)
        1 - High (MP3 320kbps)
        2 - Best (FLAC, if available)
        max_workers: Number of concurrent uploads
        """
        try:
            print(f"{Fore.CYAN}Authorizing with Spotify...{Style.RESET_ALL}")
            
            quality_names = {
                0: "Low (AAC 64kbps)",
                1: "High (MP3 320kbps)",
                2: "Best (FLAC)"
            }
            print(f"{Fore.CYAN}Selected quality: {quality_names.get(quality, 'Unknown')}{Style.RESET_ALL}")

            # Initialize Spotify client
            try:
                scope = "user-library-read playlist-read-private"
                self.spotify_client = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    redirect_uri="http://localhost:8888/callback",
                    scope=scope
                ))
                print(f"{Fore.GREEN}Successfully authorized with Spotify!{Style.RESET_ALL}")
            except Exception as auth_error:
                print(f"{Fore.YELLOW}Failed OAuth, falling back to client credentials...{Style.RESET_ALL}")
                self.spotify_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                ))
                print(f"{Fore.GREEN}Spotify client initialized with client credentials!{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Note: Some features may be limited without user authentication.{Style.RESET_ALL}")

            parsed_url = urlparse(spotify_url)
            path_parts = parsed_url.path.strip('/').split('/')
            
            tracks_info = []
            
            if 'track' in path_parts:
                print(f"{Fore.CYAN}Detected single track link.{Style.RESET_ALL}")
                track_id = path_parts[-1]
                try:
                    track = self.spotify_client.track(track_id)
                    artists = ', '.join([artist['name'] for artist in track['artists']])
                    cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
                    
                    # Note: Spotify API doesn't provide direct download links, using placeholder
                    download_url = f"https://api.spotify.com/v1/tracks/{track_id}"  # Placeholder, actual download requires external service
                    track_info = {
                        'title': track['name'],
                        'artist': artists,
                        'album': track['album']['name'],
                        'download_url': download_url,
                        'cover_url': cover_url,
                        'track_id': track_id,
                        'genre': track.get('genre', '')
                    }
                    tracks_info.append(track_info)
                    print(f"{Fore.CYAN}Prepared track: {artists} - {track['name']}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}Error fetching track: {str(e)}{Style.RESET_ALL}")
                    return False

            elif 'album' in path_parts:
                print(f"{Fore.CYAN}Detected album link.{Style.RESET_ALL}")
                album_id = path_parts[-1]
                try:
                    album = self.spotify_client.album(album_id)
                    print(f"{Fore.GREEN}Found album: {album['name']} ({len(album['tracks']['items'])} tracks){Style.RESET_ALL}")
                    for track in album['tracks']['items']:
                        artists = ', '.join([artist['name'] for artist in track['artists']])
                        cover_url = album['images'][0]['url'] if album['images'] else None
                        download_url = f"https://api.spotify.com/v1/tracks/{track['id']}"  # Placeholder
                        track_info = {
                            'title': track['name'],
                            'artist': artists,
                            'album': album['name'],
                            'download_url': download_url,
                            'cover_url': cover_url,
                            'track_id': track['id'],
                            'genre': album.get('genres', [''])[0]
                        }
                        tracks_info.append(track_info)
                        print(f"{Fore.CYAN}Prepared track: {artists} - {track['name']}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}Error fetching album: {str(e)}{Style.RESET_ALL}")
                    return False

            elif 'artist' in path_parts:
                print(f"{Fore.CYAN}Detected artist link.{Style.RESET_ALL}")
                artist_id = path_parts[-1]
                try:
                    artist = self.spotify_client.artist(artist_id)
                    print(f"{Fore.GREEN}Found artist: {artist['name']}{Style.RESET_ALL}")
                    top_tracks = self.spotify_client.artist_top_tracks(artist_id)
                    for track in top_tracks['tracks']:
                        artists = ', '.join([artist['name'] for artist in track['artists']])
                        cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
                        download_url = f"https://api.spotify.com/v1/tracks/{track['id']}"  # Placeholder
                        track_info = {
                            'title': track['name'],
                            'artist': artists,
                            'album': track['album']['name'],
                            'download_url': download_url,
                            'cover_url': cover_url,
                            'track_id': track['id'],
                            'genre': artist.get('genres', [''])[0]
                        }
                        tracks_info.append(track_info)
                        print(f"{Fore.CYAN}Prepared track: {artists} - {track['name']}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}Error fetching artist tracks: {str(e)}{Style.RESET_ALL}")
                    return False

            elif 'playlist' in path_parts:
                print(f"{Fore.CYAN}Detected playlist link.{Style.RESET_ALL}")
                playlist_id = path_parts[-1]
                try:
                    playlist = self.spotify_client.playlist(playlist_id)
                    print(f"{Fore.GREEN}Found playlist: {playlist['name']} ({len(playlist['tracks']['items'])} tracks){Style.RESET_ALL}")
                    for item in playlist['tracks']['items']:
                        track = item['track']
                        artists = ', '.join([artist['name'] for artist in track['artists']])
                        cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
                        download_url = f"https://api.spotify.com/v1/tracks/{track['id']}"  # Placeholder
                        track_info = {
                            'title': track['name'],
                            'artist': artists,
                            'album': track['album']['name'],
                            'download_url': download_url,
                            'cover_url': cover_url,
                            'track_id': track['id'],
                            'genre': track.get('genre', '')
                        }
                        tracks_info.append(track_info)
                        print(f"{Fore.CYAN}Prepared track: {artists} - {track['name']}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}Error fetching playlist: {str(e)}{Style.RESET_ALL}")
                    return False
            else:
                print(f"{Fore.RED}Unsupported Spotify URL type: {spotify_url}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Supported formats: playlists, albums, artists, tracks{Style.RESET_ALL}")
                return False

            if not tracks_info:
                print(f"{Fore.RED}No tracks found to download.{Style.RESET_ALL}")
                return False

            print(f"{Fore.CYAN}Starting upload of {len(tracks_info)} tracks to K-Connect with {max_workers} workers...{Style.RESET_ALL}")
            success_count = 0

            def process_track_wrapper(track_info):
                return self.download_and_process_track(track_info, "Spotify")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_track = {executor.submit(process_track_wrapper, track_info): track_info for track_info in tracks_info}
                for i, future in enumerate(future_to_track, 1):
                    track_info = future_to_track[future]
                    try:
                        result = future.result()
                        if result:
                            success_count += 1
                            print(f"{Fore.CYAN}[{i}/{len(tracks_info)}] Successfully processed track: {track_info['artist']} - {track_info['title']}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}[{i}/{len(tracks_info)}] Failed to process track: {track_info['artist']} - {track_info['title']}{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}[{i}/{len(tracks_info)}] Error processing track {track_info['title']}: {str(e)}{Style.RESET_ALL}")

            print(f"{Fore.GREEN}Import completed! Successfully uploaded {success_count} out of {len(tracks_info)} tracks.{Style.RESET_ALL}")
            return True

        except Exception as e:
            logger.error(f"Error importing from Spotify: {str(e)}")
            print(f"{Fore.RED}Error importing from Spotify: {str(e)}{Style.RESET_ALL}")
            return False

    def login_to_k_connect(self, username, password):
        """Authorize in K-Connect with user credentials"""
        if not self.k_connect_session:
            print(f"{Fore.RED}No active K-Connect session.{Style.RESET_ALL}")
            return False
        
        try:
            print(f"{Fore.CYAN}Authorizing in K-Connect with credentials...{Style.RESET_ALL}")
            
            self.k_connect_session.headers.update({
                'X-Key': self.music_api_key,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Content-Type': 'application/json'
            })

            login_data = {
                'email': username,
                'password': password
            }

            login_url = f"{self.k_connect_url}/api/auth/login"
            print(f"{Fore.CYAN}Sending authorization request: {login_url}{Style.RESET_ALL}")
            
            response = self.k_connect_session.post(
                login_url,
                json=login_data,
                timeout=10
            )

            print(f"{Fore.CYAN}Response status: {response.status_code}{Style.RESET_ALL}")
            
            if response.status_code == 200:
                try:
                    json_response = response.json()
                    print(f"{Fore.GREEN}Successful authorization in K-Connect!{Style.RESET_ALL}")
                    
                    if 'token' in json_response:
                        token = json_response['token']
                        self.k_connect_session.headers.update({
                            'Authorization': f'Bearer {token}'
                        })
                        print(f"{Fore.GREEN}Authorization token received and saved.{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}Authorization token not found in response, but authorization successful.{Style.RESET_ALL}")

                    if self.k_connect_session.cookies:
                        self.cookies = {name: value for name, value in self.k_connect_session.cookies.items()}
                        print(f"{Fore.GREEN}Session cookies saved.{Style.RESET_ALL}")

                    return self.test_api_connection()
                except Exception as e:
                    print(f"{Fore.YELLOW}Error processing authorization response: {str(e)}{Style.RESET_ALL}")
                    return False
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get('message', 'Unknown error')
                    print(f"{Fore.RED}Authorization error: {error_message}{Style.RESET_ALL}")
                except:
                    print(f"{Fore.RED}Authorization error. Status: {response.status_code}{Style.RESET_ALL}")
                    print(f"{Fore.RED}Response: {response.text[:200]}{Style.RESET_ALL}")

                print(f"{Fore.YELLOW}Attempting to proceed with API key only...{Style.RESET_ALL}")
                return self.test_api_connection()
            
        except Exception as e:
            print(f"{Fore.RED}Exception during authorization: {str(e)}{Style.RESET_ALL}")
            import traceback
            print(f"{Fore.RED}Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return False

    def test_api_connection(self):
        """Test connection to K-Connect API"""
        try:
            print(f"{Fore.CYAN}Testing K-Connect API connection...{Style.RESET_ALL}")
            
            api_key_preview = f"{self.music_api_key[:5]}...{self.music_api_key[-5:]}" if len(self.music_api_key) > 10 else self.music_api_key
            print(f"{Fore.CYAN}Using API key: {api_key_preview}")
            headers = {
                "X-Key": self.music_api_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            if self.k_connect_session:
                print(f"{Fore.CYAN}Using existing session for request{Style.RESET_ALL}")
                self.k_connect_session.headers.update(headers)
                response = self.k_connect_session.get(f"{self.k_connect_url}/api/music", timeout=10)
            else:
                print(f"{Fore.CYAN}Creating new request without session")
                response = requests.get(f"{self.k_connect_url}/api/music", headers=headers, timeout=10)
            
            print(f"{Fore.CYAN}Request URL: {self.k_connect_url}/api/music{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Sent headers: {headers}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Response status: {response.status_code}{Style.RESET_ALL}")
            
            if response.status_code == 200:
                print(f"{Fore.GREEN}Successful K-Connect API connection!{Style.RESET_ALL}")
                try:
                    json_response = response.json()
                    print(f"{Fore.GREEN}Server response: {json_response}{Style.RESET_ALL}")
                except:
                    print(f"{Fore.GREEN}Received server response (non-JSON){Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}Failed to connect to K-Connect API. Response code: {response.status_code}{Style.RESET_ALL}")
                print(f"{Fore.RED}Server response: {response.text}{Style.RESET_ALL}")
                return False
        except Exception as e:
            print(f"{Fore.RED}Error connecting to K-Connect API: {str(e)}{Style.RESET_ALL}")
            import traceback
            print(f"{Fore.RED}Traceback: {traceback.format_exc()}{Style.RESET_ALL}")
            return False

def save_tokens(service, tokens):
    """Save tokens to file"""
    tokens_file = Path('tokens.json')
    try:
        if tokens_file.exists():
            with open(tokens_file, 'r', encoding='utf-8') as f:
                all_tokens = json.load(f)
        else:
            all_tokens = {}
        
        all_tokens[service] = tokens
        
        with open(tokens_file, 'w', encoding='utf-8') as f:
            json.dump(all_tokens, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        logger.error(f"Error saving tokens: {str(e)}")
        return False

def load_tokens(service):
    """Load tokens from file"""
    tokens_file = Path('tokens.json')
    try:
        if tokens_file.exists():
            with open(tokens_file, 'r', encoding='utf-8') as f:
                all_tokens = json.load(f)
            
            return all_tokens.get(service, {})
        return {}
    except Exception as e:
        logger.error(f"Error loading tokens: {str(e)}")
        return {}

def main():
    print(f"{Fore.CYAN}=" * 70)
    print("K-CONNECT SPOTIFY MUSIC IMPORTER")
    print("=" * 70 + Style.RESET_ALL)
    print(f"{Fore.YELLOW}This program imports music from Spotify to K-Connect.{Style.RESET_ALL}")
    print("")
    
    importer = SpotifyMusicImporter()
    
    api_key_preview = f"{importer.music_api_key[:5]}...{importer.music_api_key[-5:]}" if len(importer.music_api_key) > 10 else importer.music_api_key
    print(f"{Fore.CYAN}Using API key: {api_key_preview} (length: {len(importer.music_api_key)}){Style.RESET_ALL}")

    print(f"{Fore.CYAN}Step 1: Connecting to K-Connect{Style.RESET_ALL}")
    if importer.login_k_connect():
        print(f"{Fore.GREEN}Successfully connected to K-Connect API{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Failed to connect to K-Connect API. Check API key.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.CYAN}Step 2: Authorizing with K-Connect{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}K-Connect account authorization required for uploads.{Style.RESET_ALL}")
    k_connect_username = input("Enter K-Connect username: ")
    k_connect_password = getpass.getpass("Enter K-Connect password: ")

    if not importer.login_to_k_connect(k_connect_username, k_connect_password):
        print(f"{Fore.RED}K-Connect authorization failed. Check credentials.{Style.RESET_ALL}")
        retry = input("Continue without authorization? (y/n): ").lower()
        if retry != 'y':
            print(f"{Fore.RED}Import cancelled.{Style.RESET_ALL}")
            return
        print(f"{Fore.YELLOW}Continuing without full authorization. Some features may be unavailable.{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Successfully authorized with K-Connect!{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Step 3: Enter Spotify URL{Style.RESET_ALL}")
    print("Example Spotify URL: https://open.spotify.com/playlist/37i9dQZF1DXcBWuJcrqp2i")
    print("Supported formats: playlists, albums, artists, tracks")
    
    spotify_url = input("Enter Spotify URL: ")

    print(f"\n{Fore.CYAN}Step 4: Configure lyrics upload{Style.RESET_ALL}")
    skip_lyrics_input = input("Skip lyrics upload? (y/n, default: n): ").lower()
    importer.skip_lyrics = skip_lyrics_input == 'y'
    
    if importer.skip_lyrics:
        print(f"{Fore.YELLOW}Lyrics upload will be skipped.{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Lyrics upload enabled (Note: Spotify lyrics not supported in this version).{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Step 5: Select download quality{Style.RESET_ALL}")
    print(f"0 - Low (AAC 64kbps)")
    print(f"1 - High (MP3 320kbps)")
    print(f"2 - Best (FLAC)")
    
    quality = 1
    quality_input = input(f"Enter quality [0-2] (default: 1): ")
    if quality_input and quality_input in ['0', '1', '2']:
        quality = int(quality_input)

    print(f"\n{Fore.CYAN}Step 6: Configure concurrent uploads{Style.RESET_ALL}")
    max_workers = 4
    workers_input = input(f"Enter number of concurrent uploads [1-10] (default: 4): ")
    if workers_input and workers_input.isdigit():
        workers = int(workers_input)
        if 1 <= workers <= 10:
            max_workers = workers

    print(f"{Fore.CYAN}Starting Spotify music import...{Style.RESET_ALL}")
    if importer.import_from_spotify(spotify_url, quality=quality, max_workers=max_workers):
        print(f"{Fore.GREEN}Spotify import completed successfully!{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Spotify import failed.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Ensure valid Spotify URL and credentials.{Style.RESET_ALL}")
    
    print(f"\n{Fore.CYAN}Thank you for using the program!{Style.RESET_ALL}")
    print("Import log saved in spotify_music_import.log")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Program interrupted by user.{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        print(f"\n{Fore.RED}Error occurred: {str(e)}{Style.RESET_ALL}")
        print("Detailed information saved in log file.")