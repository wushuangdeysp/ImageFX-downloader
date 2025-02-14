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
                                    on_thread_complete=None): # 修改: on_thread_complete 接收下载结果
    """
    使用 mediaKey 下载原图和提示词，并按日期保存到子文件夹 (修改后版本)
    """
    api_url = "https://labs.google/fx/api/trpc/media.fetchMedia"
    params = {
        "input": '{"json":{"mediaKey":"' + media_key + '","height":null,"width":null},"meta":{"values":{"height":["undefined"],"width":["undefined"]}}}'
    }
    session = requests.Session()
    retries = Retry(total=total_retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist)
    session.mount("https://", HTTPAdapter(max_retries=retries))

    success = False #  标记下载是否成功
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
                        print(f"  -> 警告: 未在响应中找到提示词 for {media_key}")
                    success = True #  标记为成功

                except Exception as e:
                    print(f"  -> 保存图片/提示词 {media_key} 失败: {e}")
            else:
                print(f"  -> 下载 media.fetchMedia 失败，响应中缺少 encodedImage for {media_key}")

        else:
            print(f"  -> 下载 media.fetchMedia 失败，状态码: {response.status_code}")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"  -> 下载 media.fetchMedia 请求失败 (mediaKey: {media_key}): {e}")

    finally:
        if on_thread_complete:
            on_thread_complete(success) # 修改: 将下载结果传递给回调函数


def main():
    """
    主函数： 获取 mediaKey 列表并批量多线程下载图片和提示词 (最终多线程版本 - 移除边抓边下模式)
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

    load_from_file_prompt = input("是否加载已保存的抓取结果并直接进入批量下载模式？  \n"
                                  "如果您是第一次运行那么应该选择no (yes/no，默认: no): ").lower()
    if load_from_file_prompt in ['yes', 'y']:
        media_keys_info = []
        if os.path.exists(crawl_result_file):
            try:
                with open(crawl_result_file, 'r', encoding='utf-8') as f:
                    media_keys_info = json.load(f)
                print(f"成功从文件 '{crawl_result_file}' 加载了 {len(media_keys_info)} 张图片链接。")
                if media_keys_info:
                    cookie_string = input("请粘贴您的 Cookie 字符串 \n"
                                          "**Cookie 获取方法:**  通常在浏览器开发者工具 (F12) -> 网络 (Network) -> 任意请求的 'Cookie' 或 '请求头' (Request Headers) 中可以找到。\n"
                                          "**作用:**  用于程序模拟您的浏览器行为，访问和下载您的图片数据。\n"
                                          "**注意:**  请务必复制完整的 Cookie 字符串，包括所有字段，否则程序可能无法正常工作。\n"
                                          "请输入您的 Cookie 字符串: ")
                    if not cookie_string:
                        print("Cookie 字符串不能为空，请重新运行程序并输入 Cookie。")
                        return
                    cookies = {'Cookie': cookie_string}
                    print("")
                    print("********************")
                    print("")

                    max_threads_input = input(f"请输入多线程同时下载数量上限 (默认: {max_threads}, 建议: 1-20): ")
                    if max_threads_input.isdigit():
                        max_threads = int(max_threads_input)
                    elif max_threads_input:
                        print("线程数上限请输入数字，将使用默认值。")
                    print("")
                    print("********************")
                    print("")

                    print("开始批量下载图片...")
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

                    print(f"\n下载任务完成！")
                    print(f"共下载 {downloaded_count} 张图片，保存在 '{output_folder}' 文件夹中。")
                    print(f"总耗时: {duration:.2f} 秒")
                    return

                else:
                    print("加载的链接列表为空，请选择重新抓取。")
            except Exception as e:
                print(f"加载抓取结果文件失败: {e}。请选择重新抓取。")

        else:
            print("未加载已保存的抓取结果，将进入完整下载流程。")
    print("")
    print("********************")
    print("")


    cookie_string = input("请粘贴您的 Cookie 字符串 \n"
                          "**Cookie 获取方法:**  通常在浏览器开发者工具 (F12) -> 网络 (Network) -> 任意请求的 'Cookie' 或 '请求头' (Request Headers) 中可以找到。\n"
                          "**作用:**  用于程序模拟您的浏览器行为，访问和下载您的图片数据。\n"
                          "**注意:**  请务必复制完整的 Cookie 字符串，包括所有字段，否则程序可能无法正常工作。\n"
                          "请输入您的 Cookie 字符串: ")
    if not cookie_string:
        print("Cookie 字符串不能为空，请重新运行程序并输入 Cookie。")
        return
    cookies = {'Cookie': cookie_string}
    print("")
    print("********************")
    print("")


    max_keys_str = input("请输入要下载的最大图片数量 (可选，留空则下载全部) \n"
                         "**作用:**  限制本次运行程序最多下载的图片总数。\n"
                         "**设置建议:**\n"
                         "   -  如果您只想下载最近的少量图片，可以设置一个数字，例如 '50'。\n"
                         "   -  如果您想下载所有历史图片，请直接留空，程序将自动抓取并下载所有可获取的图片。\n"
                         "请输入最大图片数量 (留空下载全部): ")
    if max_keys_str.isdigit():
        max_keys = int(max_keys_str)
        print(f"程序将尝试下载最多 {max_keys} 张图片。")
    else:
        print("将下载所有图片，直到完成或遇到错误。")
    print("")
    print("********************")
    print("")


    total_retries_input = input(f"请输入最大重试次数 (默认: {total_retries}, 建议: 5-15) \n"
                                "**作用:**  当下载图片或抓取链接失败时，程序会自动重试。\n"
                                "**设置建议:**\n"
                                "   -  网络环境不稳定时，可以适当增加重试次数。\n"
                                "   -  建议设置为 5-15 次，避免无限重试。\n"
                                f"请输入最大重试次数 (默认: {total_retries}): ")
    if total_retries_input.isdigit():
        total_retries = int(total_retries_input)
    print("")
    print("********************")
    print("")


    backoff_factor_input = input(f"请输入重试退避因子 (默认: {backoff_factor}, 建议: 0.5-2) \n"
                                 "**作用:**  控制每次重试之间的等待时间。退避因子越大，等待时间越长。\n"
                                 "**设置建议:**\n"
                                 "   -  网络请求频繁被限制时，可以适当增加退避因子，例如设置为 '1' 或 '2'。\n"
                                 "   -  通常情况下，默认值 '1' 即可。\n"
                                 f"请输入重试退避因子 (默认: {backoff_factor}): ")
    if backoff_factor_input:
        backoff_factor = float(backoff_factor_input)
    print("")
    print("********************")
    print("")


    status_forcelist_input = input(f"请输入需要重试的状态码 (默认: {status_forcelist}，多个用逗号分隔，留空则使用默认) \n"
                                  "**作用:**  指定哪些 HTTP 状态码被认为是下载失败，需要重试。\n"
                                  "**设置建议:**\n"
                                  "   -  默认状态码 {status_forcelist}  (429, 500, 502, 503, 504)  表示服务器繁忙或网络错误。\n"
                                  "   -  通常情况下，保持默认即可。除非您明确知道需要针对其他状态码进行重试。\n"
                                  "   -  多个状态码用逗号 ',' 分隔，例如 '429, 500, 503'。\n"
                                  f"请输入需要重试的状态码 (默认: {status_forcelist}，留空则使用默认): ")
    if status_forcelist_input:
        status_forcelist = tuple(int(code.strip()) for code in status_forcelist_input.split(','))
    print("")
    print("********************")
    print("")


    page_sleep_time_input = input(f"请输入页面请求延时(秒) (默认: {page_sleep_time}, 建议: 1-5, 可适当增加) \n"
                                  "**作用:**  程序在抓取多页图片链接时，每页请求后暂停的时间，避免请求过快被服务器限制。\n"
                                  "**设置建议:**\n"
                                  "   -  如果抓取速度过快导致错误，可以适当增加延时，例如设置为 '2' 或 '3'。\n"
                                  "   -  通常情况下，默认值 '1' 秒即可。\n"
                                  f"请输入页面请求延时(秒) (默认: {page_sleep_time}): ")
    if page_sleep_time_input.isdigit():
        page_sleep_time = int(page_sleep_time_input)
    print("")
    print("********************")
    print("")


    max_threads_input = input(f"请输入多线程同时下载数量上限 (默认: {max_threads}, 建议: 1-20) \n"
                              "**作用:**  控制同时下载图片的线程数量，提高下载速度。\n"
                              "**设置建议:**\n"
                              "   -  线程数过高可能会增加服务器压力，并可能导致您自己的网络拥堵。\n"
                              "   -  线程数过低则下载速度较慢。\n"
                              "   -  建议范围为 1-20，根据您的网络环境和电脑性能调整。\n"
                              f"请输入多线程同时下载数量上限 (默认: {max_threads}): ")
    if max_threads_input.isdigit():
        max_threads = int(max_threads_input)
    elif max_threads_input:
        print("线程数上限请输入数字，将使用默认值。")
    print("")
    print("********************")
    print("")

    downloaded_count = 0
    start_time = time.time()

    #  ---  以下代码块移除了关于 download_threshold 的判断，始终执行先抓后下模式  ---
    print(f"\n---  将始终采用先抓取链接再批量下载模式  ---")

    print("开始抓取图片链接和创建时间...")
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
            print(f"成功将抓取结果保存到文件 '{crawl_result_file}'。")
        except Exception as e:
            print(f"保存抓取结果到文件失败: {e}")

        if media_keys_info:
            user_confirmation = input(f"链接抓取完成，共抓取到 {len(media_keys_info)} 张图片链接。是否开始下载图片？ (yes/no，默认: no): ")
            if user_confirmation.lower() in ['yes', 'y']:
                print("开始批量下载图片...")
                downloader = BatchDownloader(
                    cookies, output_folder,
                    total_retries=total_retries, backoff_factor=backoff_factor,
                    status_forcelist=status_forcelist,
                    max_threads=max_threads,
                )
                downloaded_count = downloader.download_media_keys(media_keys_info)
            else:
                print("用户取消下载。")
        else:
            print("链接抓取失败，请检查错误信息。未开始下载。")

    # ---  移除 else 分支，只保留先抓后下模式的代码结束  ---


    end_time = time.time()
    duration = end_time - start_time

    print(f"\n下载任务完成！")
    print(f"共下载 {downloaded_count} 张图片，保存在 '{output_folder}' 文件夹中。")
    print(f"总耗时: {duration:.2f} 秒")


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
                                print(f"已达到最大抓取链接数量 {self.max_keys}，停止获取更多 mediaKey。")
                                break
                    else:
                        print("警告: 响应中 userWorkflows 为空，但包含 nextPageToken，继续尝试下一页。")
                elif 'result' in response_json and 'data' in response_json['result'] and 'json' in response_json['result']['data'] and \
                     'result' in response_json['result']['data']['json'] and 'nextPageToken' in response_json['result']['data']['json']['result']:
                    print("警告: 响应中缺少 userWorkflows，但包含 nextPageToken，继续尝试下一页。")
                else:
                    print("警告: 响应格式异常，可能缺少 userWorkflows 或 nextPageToken。")
                    has_next_page = False

                if not has_next_page:
                    break

                next_page_token = response_json['result']['data']['json']['result'].get('nextPageToken', "")
                has_next_page = bool(next_page_token)
                if has_next_page and (not self.max_keys or media_keys_count < self.max_keys):
                    print(f"已抓取 {media_keys_count} 张图片链接, 剩余页面: {has_next_page}")
                    time.sleep(self.page_sleep_time)

            else:
                print(f"获取 media.fetchUserHistory 失败，状态码: {response.status_code}")
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
        self.success_count = 0 #  BatchDownloader 内置成功计数器

    def download_media_keys(self, media_keys_info):
        downloaded_count = 0
        for index, item in enumerate(media_keys_info): #  使用 enumerate 获取索引
            media_key = item['media_key']
            create_time = item['create_time']

            while self.active_threads_count >= self.max_threads:
                time.sleep(0.1)
                self.threads = [t for t in self.threads if t.is_alive()]
                self.active_threads_count = len(self.threads)

            thread = threading.Thread(
                target=download_image_and_prompt,
                args=(media_key, self.cookies, self.output_folder, create_time),
                kwargs={'on_thread_complete': lambda result, mk=media_key: self.update_thread_completion(result, mk)} # 修改: lambda 接收 result 和 media_key
            )
            self.threads.append(thread)
            thread.start()
            self.active_threads_count += 1

        for thread in self.threads:
            thread.join()

        #  下载完成后，打印最终成功下载总数
        print(f"\n批量下载完成，成功下载 {self.success_count} 张图片。") # 最终总结
        return self.success_count # 返回成功下载数量


    def update_thread_completion(self, result, media_key): # 修改: 接收 result 和 media_key
        self.active_threads_count -= 1
        if result:
            self.success_count += 1 #  成功时增加计数
            if self.success_count % 10 == 0: #  每成功下载 10 张打印一次
                print(f"已成功下载 {self.success_count} 张图片...") #  批量成功提示
        else:
            print(f"  -> 图片 {media_key}.jpg 下载失败.") #  失败时打印具体 media_key


if __name__ == "__main__":
    main()
