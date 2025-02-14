import requests
from requests.adapters import Retry, HTTPAdapter
import json
import base64
import os
import time
import threading
from datetime import datetime

def download_image_and_prompt(media_key, cookies, output_folder="imagefx_images", create_time=None,
                                     total_retries=10, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                                     on_thread_complete=None): # Modified: on_thread_complete receives download result
    """
    Downloads the original image and prompt using mediaKey, and saves them to subfolders by date (modified version)
    """
    api_url = "https://labs.google/fx/api/trpc/media.fetchMedia"
    params = {
        "input": '{"json":{"mediaKey":"' + media_key + '","height":null,"width":null},"meta":{"values":{"height":["undefined"],"width":["undefined"]}}}'
    }
    session = requests.Session()
    retries = Retry(total=total_retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist)
    session.mount("https://", HTTPAdapter(max_retries=retries))

    success = False # Flag indicating whether the download was successful
    try:
        response = session.get(api_url, params=params, cookies=cookies, timeout=30)
        response.encoding = 'utf-8'

        if response.status_code == 200:
            response_json = response.json()
            result_data_json_result = response_json['result']['data']['json']['result']
            encoded_image = result_data_json_result['image']['encodedImage']
            prompt_text = result_data_json_result.get('image').get('prompt')

            if encoded_image:
                try:
                    image_data = base64.b64decode(encoded_image)

                    if create_time:
                        date_object = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
                        date_folder_name = date_object.strftime("%Y-%m-%d")
                        date_folder_path = os.path.join(output_folder, date_folder_name)
                        os.makedirs(date_folder_path, exist_ok=True)

                        image_filename = os.path.join(date_folder_path, f"{media_key}.jpg")
                        prompt_filename = os.path.join(date_folder_path, f"{media_key}.txt")
                    else:
                        image_filename = os.path.join(output_folder, f"{media_key}.jpg")
                        prompt_filename = os.path.join(output_folder, f"{media_key}.txt")

                    with open(image_filename, "wb") as f:
                        f.write(image_data)

                    if prompt_text:
                        with open(prompt_filename, "w", encoding='utf-8') as f:
                            f.write(prompt_text)
                    else:
                        print(f"  -> Warning: Prompt text not found in response for {media_key}")
                    success = True # Mark as successful

                except Exception as e:
                    print(f"  -> Failed to save image/prompt {media_key}: {e}")
            else:
                print(f"  -> Failed to download media.fetchMedia, encodedImage missing in response for {media_key}")

        else:
            print(f"  -> Failed to download media.fetchMedia, status code: {response.status_code}")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"  -> Request to download media.fetchMedia failed (mediaKey: {media_key}): {e}")

    finally:
        if on_thread_complete:
            on_thread_complete(success) # Modified: Pass the download result to the callback function


def main():
    """
    Main function: Gets mediaKey list and downloads images and prompts in batches using multi-threading (final multi-threading version - removed on-the-fly download mode)
    """
    output_folder = "imagefx_images"
    os.makedirs(output_folder, exist_ok=True)
    crawl_result_file = "media_keys_crawl_result.json"

    total_retries = 10
    backoff_factor = 1
    status_forcelist = (429, 500, 502, 503, 504)
    page_sleep_time = 1
    max_keys = None
    max_threads = 10

    load_from_file_prompt = input("Load saved crawl results and directly enter batch download mode? \n"
                                     "If you are running for the first time, you should choose 'no' (yes/no, default: no): ").lower()
    if load_from_file_prompt in ['yes', 'y']:
        media_keys_info = []
        if os.path.exists(crawl_result_file):
            try:
                with open(crawl_result_file, 'r', encoding='utf-8') as f:
                    media_keys_info = json.load(f)
                print(f"Successfully loaded {len(media_keys_info)} image links from file '{crawl_result_file}'.")
                if media_keys_info:
                    cookie_string = input("Please paste your Cookie string \n"
                                             "**How to get Cookie:** Usually found in browser developer tools (F12) -> Network -> any request's 'Cookie' or 'Request Headers'.\n"
                                             "**Purpose:** Used by the program to simulate your browser behavior, to access and download your image data.\n"
                                             "**Note:** Please make sure to copy the complete Cookie string, including all fields, otherwise the program may not work properly.\n"
                                             "Please enter your Cookie string: ")
                    if not cookie_string:
                        print("Cookie string cannot be empty. Please re-run the program and enter Cookie.")
                        return
                    cookies = {'Cookie': cookie_string}
                    print("")
                    print("********************")
                    print("")

                    max_threads_input = input(f"Enter the maximum number of threads for concurrent downloads (default: {max_threads}, recommended: 1-20): ")
                    if max_threads_input.isdigit():
                        max_threads = int(max_threads_input)
                    elif max_threads_input:
                        print("Please enter a number for the thread limit. Default value will be used.")
                    print("")
                    print("********************")
                    print("")

                    print("Starting batch download of images...")
                    downloader = BatchDownloader(
                        cookies, output_folder,
                        total_retries=total_retries, backoff_factor=backoff_factor,
                        status_forcelist=status_forcelist,
                        max_threads=max_threads
                    )
                    start_time = time.time()
                    downloaded_count = downloader.download_media_keys(media_keys_info)
                    end_time = time.time()
                    duration = end_time - start_time

                    print(f"\nDownload task completed!")
                    print(f"Downloaded {downloaded_count} images in total, saved in '{output_folder}' folder.")
                    print(f"Total time spent: {duration:.2f} seconds")
                    return

                else:
                    print("Loaded link list is empty, please choose to re-crawl.")
            except Exception as e:
                print(f"Failed to load crawl result file: {e}. Please choose to re-crawl.")

        else:
            print("Saved crawl results not loaded, will enter full download process.")
    print("")
    print("********************")
    print("")


    cookie_string = input("Please paste your Cookie string \n"
                             "**How to get Cookie:** Usually found in browser developer tools (F12) -> Network -> any request's 'Cookie' or 'Request Headers'.\n"
                             "**Purpose:** Used by the program to simulate your browser behavior, to access and download your image data.\n"
                             "**Note:** Please make sure to copy the complete Cookie string, including all fields, otherwise the program may not work properly.\n"
                             "Please enter your Cookie string: ")
    if not cookie_string:
        print("Cookie string cannot be empty. Please re-run the program and enter Cookie.")
        return
    cookies = {'Cookie': cookie_string}
    print("")
    print("********************")
    print("")


    max_keys_str = input("Enter the maximum number of images to download (optional, leave blank to download all) \n"
                             "**Purpose:** Limits the maximum total number of images downloaded in this program run.\n"
                             "**Setting suggestions:**\n"
                             "    - If you only want to download the latest few images, you can set a number, e.g., '50'.\n"
                             "    - If you want to download all historical images, please leave it blank, the program will automatically crawl and download all available images.\n"
                             "Enter the maximum number of images (leave blank to download all): ")
    if max_keys_str.isdigit():
        max_keys = int(max_keys_str)
        print(f"Program will attempt to download at most {max_keys} images.")
    else:
        print("Will download all images until completed or an error occurs.")
    print("")
    print("********************")
    print("")


    total_retries_input = input(f"Enter the maximum number of retries (default: {total_retries}, recommended: 5-15) \n"
                                     "**Purpose:** When downloading images or crawling links fails, the program will automatically retry.\n"
                                     "**Setting suggestions:**\n"
                                     "    - When the network environment is unstable, you can increase the number of retries appropriately.\n"
                                     "    - It is recommended to set it to 5-15 times to avoid infinite retries.\n"
                                     f"Enter the maximum number of retries (default: {total_retries}): ")
    if total_retries_input.isdigit():
        total_retries = int(total_retries_input)
    print("")
    print("********************")
    print("")


    backoff_factor_input = input(f"Enter the backoff factor for retries (default: {backoff_factor}, recommended: 0.5-2) \n"
                                     "**Purpose:** Controls the waiting time between retries. The larger the backoff factor, the longer the waiting time.\n"
                                     "**Setting suggestions:**\n"
                                     "    - When network requests are frequently limited, you can increase the backoff factor appropriately, e.g., set it to '1' or '2'.\n"
                                     "    - In most cases, the default value '1' is sufficient.\n"
                                     f"Enter the backoff factor for retries (default: {backoff_factor}): ")
    if backoff_factor_input:
        backoff_factor = float(backoff_factor_input)
    print("")
    print("********************")
    print("")


    status_forcelist_input = input(f"Enter the status codes to retry (default: {status_forcelist}, multiple codes separated by commas, leave blank for default) \n"
                                      "**Purpose:** Specifies which HTTP status codes are considered download failures and need to be retried.\n"
                                      "**Setting suggestions:**\n"
                                      "    - The default status codes {status_forcelist} (429, 500, 502, 503, 504) indicate server busy or network errors.\n"
                                      "    - In most cases, keep the default. Unless you specifically know you need to retry for other status codes.\n"
                                      "    - Separate multiple status codes with commas ',', e.g., '429, 500, 503'.\n"
                                      f"Enter the status codes to retry (default: {status_forcelist}, leave blank for default): ")
    if status_forcelist_input:
        status_forcelist = tuple(int(code.strip()) for code in status_forcelist_input.split(','))
    print("")
    print("********************")
    print("")


    page_sleep_time_input = input(f"Enter page request delay (seconds) (default: {page_sleep_time}, recommended: 1-5, can be increased appropriately) \n"
                                     "**Purpose:** The pause time after each page request when the program crawls multiple pages of image links, to avoid requests being too fast and being limited by the server.\n"
                                     "**Setting suggestions:**\n"
                                     "    - If crawling speed is too fast causing errors, you can increase the delay appropriately, e.g., set to '2' or '3'.\n"
                                     "    - In most cases, the default value '1' second is sufficient.\n"
                                     f"Enter page request delay (seconds) (default: {page_sleep_time}): ")
    if page_sleep_time_input.isdigit():
        page_sleep_time = int(page_sleep_time_input)
    print("")
    print("********************")
    print("")


    max_threads_input = input(f"Enter the maximum number of threads for concurrent downloads (default: {max_threads}, recommended: 1-20) \n"
                                     "**Purpose:** Controls the number of threads for concurrent image downloads, improving download speed.\n"
                                     "**Setting suggestions:**\n"
                                     "    - Too many threads may increase server pressure and may cause congestion on your own network.\n"
                                     "    - Too few threads will result in slower download speeds.\n"
                                     "    - Recommended range is 1-20, adjust according to your network environment and computer performance.\n"
                                     f"Enter the maximum number of threads for concurrent downloads (default: {max_threads}): ")
    if max_threads_input.isdigit():
        max_threads = int(max_threads_input)
    elif max_threads_input:
        print("Please enter a number for the thread limit. Default value will be used.")
    print("")
    print("********************")
    print("")

    downloaded_count = 0
    start_time = time.time()

    # --- The following code block removes the judgment about download_threshold, and always executes the mode of crawling links first and then downloading in batches ---
    print(f"\n--- Will always use the mode of crawling links first and then downloading in batches ---")

    print("Starting to crawl image links and creation times...")
    media_keys_crawler = MediaKeyCrawler(
        cookies, max_keys,
        total_retries=total_retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist,
        page_sleep_time=page_sleep_time
    )
    media_keys_info = media_keys_crawler.get_all_media_keys_info()

    if media_keys_info:
        try:
            with open(crawl_result_file, 'w', encoding='utf-8') as f:
                json.dump(media_keys_info, f, ensure_ascii=False, indent=4)
            print(f"Successfully saved crawl results to file '{crawl_result_file}'.")
        except Exception as e:
            print(f"Failed to save crawl results to file: {e}")

        if media_keys_info:
            user_confirmation = input(f"Link crawling completed, {len(media_keys_info)} image links crawled. Start downloading images? (yes/no, default: no): ")
            if user_confirmation.lower() in ['yes', 'y']:
                print("Starting batch download of images...")
                downloader = BatchDownloader(
                    cookies, output_folder,
                    total_retries=total_retries, backoff_factor=backoff_factor,
                    status_forcelist=status_forcelist,
                    max_threads=max_threads,
                )
                downloaded_count = downloader.download_media_keys(media_keys_info)
            else:
                print("User cancelled download.")
        else:
            print("Link crawling failed, please check error messages. Download not started.")

    # --- Removed else branch, only keeping the code for crawl-first and then download mode ---


    end_time = time.time()
    duration = end_time - start_time

    print(f"\nDownload task completed!")
    print(f"Downloaded {downloaded_count} images in total, saved in '{output_folder}' folder.")
    print(f"Total time spent: {duration:.2f} seconds")


class MediaKeyCrawler:
    def __init__(self, cookies, max_keys=None, total_retries=10, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), page_sleep_time=1):
        self.cookies = cookies
        self.max_keys = max_keys
        self.total_retries = total_retries
        self.backoff_factor = backoff_factor
        self.status_forcelist = status_forcelist
        self.page_sleep_time = page_sleep_time
        self.session = requests.Session()
        retries = Retry(total=self.total_retries, backoff_factor=self.backoff_factor, status_forcelist=self.status_forcelist)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def get_all_media_keys_info(self):
        media_keys_info = []
        media_keys_count = 0
        next_page_token = ""
        has_next_page = True

        while has_next_page:
            api_url = "https://labs.google/fx/api/trpc/media.fetchUserHistory"
            params = {
                "input": '{"json":{"cursor":"' + next_page_token + '","limit":12, "type":"IMAGE_FX"},"meta":{"values":{}}}'
            }
            try:
                response = self.session.get(api_url, params=params, cookies=self.cookies, timeout=30)
            except requests.exceptions.RequestException as e:
                print(f"Error fetching media.fetchUserHistory in MediaKeyCrawler: {e}")
                has_next_page = False
                break

            if response.status_code == 200:
                response_json = response.json()
                if 'result' in response_json and 'data' in response_json['result'] and 'json' in response_json['result']['data'] and \
                   'result' in response_json['result']['data']['json'] and 'userWorkflows' in response_json['result']['data']['json']['result']:
                    user_workflows = response_json['result']['data']['json']['result']['userWorkflows']

                    if user_workflows:
                        for workflow in user_workflows:
                            media_key = workflow['name']
                            create_time = workflow['createTime']
                            media_keys_info.append({'media_key': media_key, 'create_time': create_time})
                            media_keys_count += 1

                            if self.max_keys and media_keys_count >= self.max_keys:
                                has_next_page = False
                                print(f"Reached maximum number of crawled links {self.max_keys}, stopped getting more mediaKeys.")
                                break
                    else:
                        print("Warning: userWorkflows is empty in response, but contains nextPageToken, continue trying next page.")
                elif 'result' in response_json and 'data' in response_json['result'] and 'json' in response_json['result']['data'] and \
                     'result' in response_json['result']['data']['json'] and 'nextPageToken' in response_json['result']['data']['json']['result']:
                    print("Warning: userWorkflows is missing in response, but contains nextPageToken, continue trying next page.")
                else:
                    print("Warning: Response format is abnormal, may be missing userWorkflows or nextPageToken.")
                    has_next_page = False

                if not has_next_page:
                    break

                next_page_token = response_json['result']['data']['json']['result'].get('nextPageToken', "")
                has_next_page = bool(next_page_token)
                if has_next_page and (not self.max_keys or media_keys_count < self.max_keys):
                    print(f"Crawled {media_keys_count} image links, remaining pages: {has_next_page}")
                    time.sleep(self.page_sleep_time)

            else:
                print(f"Failed to get media.fetchUserHistory, status code: {response.status_code}")
                print(response.text)
                has_next_page = False

        return media_keys_info


class BatchDownloader:
    def __init__(self, cookies, output_folder, total_retries=10, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), max_threads=10):
        self.cookies = cookies
        self.output_folder = output_folder
        self.total_retries = total_retries
        self.backoff_factor = backoff_factor
        self.status_forcelist = status_forcelist
        self.max_threads = max_threads
        self.active_threads_count = 0
        self.threads = []
        self.success_count = 0 # Built-in success counter for BatchDownloader

    def download_media_keys(self, media_keys_info):
        downloaded_count = 0
        for index, item in enumerate(media_keys_info): # Use enumerate to get index
            media_key = item['media_key']
            create_time = item['create_time']

            while self.active_threads_count >= self.max_threads:
                time.sleep(0.1)
                self.threads = [t for t in self.threads if t.is_alive()]
                self.active_threads_count = len(self.threads)

            thread = threading.Thread(
                target=download_image_and_prompt,
                args=(media_key, self.cookies, self.output_folder, create_time),
                kwargs={'on_thread_complete': lambda result, mk=media_key: self.update_thread_completion(result, mk)} # Modified: lambda receives result and media_key
            )
            self.threads.append(thread)
            thread.start()
            self.active_threads_count += 1

        for thread in self.threads:
            thread.join()

        # After download is complete, print the final total number of successful downloads
        print(f"\nBatch download completed, {self.success_count} images downloaded successfully.") # Final summary
        return self.success_count # Return the number of successful downloads


    def update_thread_completion(self, result, media_key): # Modified: Receives result and media_key
        self.active_threads_count -= 1
        if result:
            self.success_count += 1 # Increase count on success
            if self.success_count % 10 == 0: # Print every 10 successful downloads
                print(f"Successfully downloaded {self.success_count} images...") # Batch success prompt
        else:
            print(f"  -> Image {media_key}.jpg download failed.") # Print specific media_key on failure


if __name__ == "__main__":
    main()
