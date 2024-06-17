import os
import re
import json
import arxiv
import yaml
import logging
import argparse
import datetime
import requests
from typing import Optional
import time
import google.generativeai as genai


# https://github.com/google-gemini/cookbook/tree/main
# https://ai.google.dev/api?hl=zh-cn
class Translater:
    def __init__(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=self.api_key)  # 填入自己的api_key

        # 查询模型
        for m in genai.list_models():
            print(m.name)
            print(m.supported_generation_methods)
        sys_prompt = (
            "You are a highly skilled translator specializing in artificial intelligence and computer science. \
            You pride yourself on incredible accuracy and attention to detail. You always stick to the facts in the sources provided, and never make up new facts.\
            Your translations are known for their accuracy, clarity, and fluency.\n\
            Your task is to translate technical academic abstracts from English to Simplified Chinese.\
            You will receive an English abstract, and you should produce a Chinese translation that adheres to the following:\n\
            * **Accuracy:** All technical terms and concepts must be translated correctly.\n\
            * **Clarity:** The translation should be easily understood by someone familiar with AI concepts.\n\
            * **Fluency:** The translation should read naturally in Chinese.\n\
            * **Output Format:** The returned text should not be bolded, not be separated into paragraphs, and remove all line breaks to merge into a single paragraph.\n \
            Do not add your own opinions or interpretations; remain faithful to the original text while optimizing for readability. \
            "
        )

        self.model = genai.GenerativeModel(
            "gemini-1.5-pro-latest",
            system_instruction=sys_prompt,
            generation_config=genai.GenerationConfig(
                # max_output_tokens=2000,
                temperature=0.8,
            ),
        )

    # models/gemini-pro
    # 输入令牌限制:30720
    # 输出令牌限制:2048
    # 模型安全:自动应用的安全设置，可由开发者调整。如需了解详情，请参阅安全设置

    def translate(self, text: str):
        retry_count = 0
        retry_seconds = 1
        NUM_RETRIES = 3
        while retry_count < NUM_RETRIES:
            try:
                response = self.model.generate_content(
                    f"Note output format, here is the abstract to translate:\n{text}"
                )
                result = response.text
                print(result)
                break
            except Exception as e:
                print(f"Received {e} error, retry after {retry_seconds} seconds.")
                time.sleep(retry_seconds)
                retry_count += 1
                # Here exponential backoff is employed to ensure
                # the account doesn't get rate limited by making
                # too many requests too quickly. This increases the
                # time to wait between requests by a factor of 2.
                retry_seconds *= 2
            finally:
                if retry_count == NUM_RETRIES:
                    print("Could not recover after making " f"{retry_count} attempts.")
                    result = text

        return result


logging.basicConfig(
    format="[%(asctime)s %(levelname)s] %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)

base_url = "https://arxiv.paperswithcode.com/api/v0/papers/"
github_url = "https://api.github.com/search/repositories"
arxiv_url = "http://arxiv.org/"


def load_config(config_file: str) -> dict:
    """
    config_file: input config file path
    return: a dict of configuration
    """

    # make filters pretty
    def pretty_filters(**config) -> dict:
        keywords = dict()
        EXCAPE = '"'
        QUOTA = ""  # NO-USE
        OR = " OR "  # TODO

        def parse_filters(filters: list):
            ret = ""
            for idx in range(0, len(filters)):
                filter = filters[idx]
                if len(filter.split()) > 1:
                    ret += EXCAPE + filter + EXCAPE
                else:
                    ret += QUOTA + filter + QUOTA
                if idx != len(filters) - 1:
                    ret += OR
            return ret

        for k, v in config["keywords"].items():
            keywords[k] = parse_filters(v["filters"])  # {NeRF:}
        return keywords

    with open(config_file, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        config["kv"] = pretty_filters(**config)
        logging.info(f"config = {config}")

    return config


def get_authors(authors, first_author=False):
    output = str()
    if first_author == False:
        output = ", ".join(str(author) for author in authors)
    else:
        output = authors[0]
    return output


def sort_papers(papers):
    output = dict()
    keys = list(papers.keys())
    keys.sort(reverse=True)
    for key in keys:
        output[key] = papers[key]
    return output


import requests


def get_code_link(qword: str) -> str:
    """
    This short function was auto-generated by ChatGPT.
    I only renamed some params and added some comments.
    @param qword: query string, eg. arxiv ids and paper titles
    @return paper_code in github: string, if not found, return None
    """
    # query = f"arxiv:{arxiv_id}"
    query = f"{qword}"
    params = {"q": query, "sort": "stars", "order": "desc"}
    r = requests.get(github_url, params=params)
    results = r.json()
    code_link = None
    if results["total_count"] > 0:
        code_link = results["items"][0]["html_url"]
    return code_link


def get_daily_papers(
    topic, query="slam", max_results=2, translater: Optional[Translater] = None
):
    """
    @param topic: str
    @param query: str
    @return paper_with_code: dict
    """
    # output
    content = dict()
    content_to_web = dict()
    print(f"query = {query}")
    search_engine = arxiv.Search(
        query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate
    )

    for result in search_engine.results():
        paper_id = result.get_short_id()
        paper_title = result.title
        paper_url = result.entry_id
        code_url = base_url + paper_id  # TODO
        paper_abstract = result.summary.replace("\n", " ")
        paper_authors = get_authors(result.authors)
        paper_first_author = get_authors(result.authors, first_author=True)
        primary_category = result.primary_category
        publish_time = result.published.date()
        update_time = result.updated.date()
        comments = result.comment

        if translater:
            print(f"Translating {paper_title}")
            retry_count = 0
            retry_seconds = 10
            NUM_RETRIES = 3
            while retry_count < NUM_RETRIES:
                try:
                    paper_abstract = translater.translate(paper_abstract)
                    break
                except Exception as e:
                    print(f"Received {e} error, retry after {retry_seconds} seconds.")
                    time.sleep(retry_seconds)
                    retry_count += 1
                    # Here exponential backoff is employed to ensure the account doesn't get rate limited by making
                    # too many requests too quickly. This increases the time to wait between requests by a factor of 2.
                    retry_seconds *= 2
                finally:
                    if retry_count == NUM_RETRIES:
                       print("Could not recover after making " f"{retry_count} attempts.")

        logging.info(
            f"Time = {update_time} title = {paper_title} author = {paper_first_author}"
        )

        # eg: 2108.09112v1 -> 2108.09112
        ver_pos = paper_id.find("v")
        if ver_pos == -1:
            paper_key = paper_id
        else:
            paper_key = paper_id[0:ver_pos]
        paper_url = arxiv_url + "abs/" + paper_key

        try:
            # source code link
            r = requests.get(code_url).json()
            repo_url = None
            if "official" in r and r["official"]:
                repo_url = r["official"]["url"]
            # TODO: not found, two more chances
            # else:
            #    repo_url = get_code_link(paper_title)
            #    if repo_url is None:
            #        repo_url = get_code_link(paper_key)
            if repo_url is not None:
                content[
                    paper_key
                ] = "|**{}**|**{}**|[{}]({})|**[link]({})**|**{}**|\n".format(
                    update_time,
                    paper_title,
                    paper_key,
                    paper_url,
                    repo_url,
                    paper_abstract,
                )
                content_to_web[
                    paper_key
                ] = "- {}, **{}**, Paper: [{}]({}), Code: **[{}]({})**,Abstract: **{}**".format(
                    update_time,
                    paper_title,
                    paper_url,
                    paper_url,
                    repo_url,
                    repo_url,
                    paper_abstract,
                )

            else:
                content[paper_key] = "|**{}**|**{}**|[{}]({})|null|**{}**|\n".format(
                    update_time, paper_title, paper_key, paper_url, paper_abstract
                )
                content_to_web[
                    paper_key
                ] = "- {}, **{}**, Paper: [{}]({}),**{}**".format(
                    update_time, paper_title, paper_url, paper_url, paper_abstract
                )

            # TODO: select useful comments
            comments = None
            if comments != None:
                content_to_web[paper_key] += f", {comments}\n"
            else:
                content_to_web[paper_key] += f"\n"

        except Exception as e:
            logging.error(f"exception: {e} with id: {paper_key}")

    data = {topic: content}
    data_web = {topic: content_to_web}
    return data, data_web


def update_paper_links(filename):
    """
    weekly update paper links in json file
    """

    def parse_arxiv_string(s):
        parts = s.split("|")
        date = parts[1].strip()
        title = parts[2].strip()
        arxiv_id = parts[3].strip()
        code = parts[4].strip()
        abstract = parts[5].strip()
        arxiv_id = re.sub(r"v\d+", "", arxiv_id)
        return date, title, arxiv_id, code, abstract

    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

        json_data = m.copy()

        for keywords, v in json_data.items():
            logging.info(f"keywords = {keywords}")
            for paper_id, contents in v.items():
                contents = str(contents)

                (
                    update_time,
                    paper_title,
                    paper_url,
                    code_url,
                    abstract,
                ) = parse_arxiv_string(contents)

                contents = "|{}|{}|{}|{}|{}|\n".format(
                    update_time, paper_title, paper_url, code_url, abstract
                )
                json_data[keywords][paper_id] = str(contents)
                logging.info(f"paper_id = {paper_id}, contents = {contents}")

                valid_link = False if "|null|" in contents else True
                if valid_link:
                    continue
                try:
                    code_url = base_url + paper_id  # TODO
                    r = requests.get(code_url).json()
                    repo_url = None
                    if "official" in r and r["official"]:
                        repo_url = r["official"]["url"]
                        if repo_url is not None:
                            new_cont = contents.replace(
                                "|null|", f"|**[link]({repo_url})**|"
                            )
                            logging.info(f"ID = {paper_id}, contents = {new_cont}")
                            json_data[keywords][paper_id] = str(new_cont)

                except Exception as e:
                    logging.error(f"exception: {e} with id: {paper_id}")
        # dump to json file
        with open(filename, "w") as f:
            json.dump(json_data, f)


def update_json_file(filename, data_dict):
    """
    daily update json file using data_dict
    """
    with open(filename, "r") as f:
        content = f.read()
        if not content:
            m = {}
        else:
            m = json.loads(content)

    json_data = m.copy()

    # update papers in each keywords
    for data in data_dict:
        for keyword in data.keys():
            papers = data[keyword]

            if keyword in json_data.keys():
                json_data[keyword].update(papers)
            else:
                json_data[keyword] = papers

    with open(filename, "w") as f:
        json.dump(json_data, f)


def json_to_md(
    filename,
    md_filename,
    task="",
    to_web=False,
    use_title=True,
    use_tc=True,
    use_b2t=True,
):
    """
    @param filename: str
    @param md_filename: str
    @return None
    """

    def pretty_math(s: str) -> str:
        ret = ""
        match = re.search(r"\$.*\$", s)
        if match == None:
            return s
        math_start, math_end = match.span()
        space_trail = space_leading = ""
        if s[:math_start][-1] != " " and "*" != s[:math_start][-1]:
            space_trail = " "
        if s[math_end:][0] != " " and "*" != s[math_end:][0]:
            space_leading = " "
        ret += s[:math_start]
        ret += f"{space_trail}${match.group()[1:-1].strip()}${space_leading}"
        ret += s[math_end:]
        return ret

    DateNow = datetime.date.today()
    DateNow = str(DateNow)
    DateNow = DateNow.replace("-", ".")

    with open(filename, "r") as f:
        content = f.read()
        if not content:
            data = {}
        else:
            data = json.loads(content)

    # clean README.md if daily already exist else create it
    with open(md_filename, "w+") as f:
        pass

    # write data into README.md
    with open(md_filename, "a+") as f:
        if (use_title == True) and (to_web == True):
            f.write("---\n" + "layout: default\n" + "---\n\n")

        if use_title == True:
            # f.write(("<p align="center"><h1 align="center"><br><ins>AI-ARXIV-DAILY"
            #         "</ins><br>Automatically Update AI Papers Daily</h1></p>\n"))
            f.write("## Updated on " + DateNow + "\n")
        else:
            f.write("> Updated on " + DateNow + "\n")

        # TODO: add usage
        f.write("> Usage instructions: [here](./docs/README.md#usage)\n\n")

        # Add: table of contents
        if use_tc == True:
            f.write("<details>\n")
            f.write("  <summary>Table of Contents</summary>\n")
            f.write("  <ol>\n")
            for keyword in data.keys():
                day_content = data[keyword]
                if not day_content:
                    continue
                kw = keyword.replace(" ", "-")
                f.write(f"    <li><a href=#{kw.lower()}>{keyword}</a></li>\n")
            f.write("  </ol>\n")
            f.write("</details>\n\n")

        for keyword in data.keys():
            day_content = data[keyword]
            if not day_content:
                continue
            # the head of each part
            f.write(f"## {keyword}\n\n")

            if use_title == True:
                if to_web == False:
                    f.write(
                        "|Publish Date|Title|PDF|Code|Abstract|\n"
                        + "|---|---|---|---|--------------------------------------------------|\n"
                    )
                else:
                    f.write("| Publish Date | Title | PDF | Code | Abstract |\n")
                    f.write(
                        "|:---------|:-----------------------|:------|:------|:-------------------------------------------------|\n"
                    )

            # sort papers by date
            day_content = sort_papers(day_content)

            for _, v in day_content.items():
                if v is not None:
                    f.write(pretty_math(v))  # make latex pretty

            f.write(f"\n")

            # Add: back to top
            if use_b2t:
                top_info = f"#Updated on {DateNow}"
                top_info = top_info.replace(" ", "-").replace(".", "")
                f.write(
                    f"<p align=right>(<a href={top_info.lower()}>back to top</a>)</p>\n\n"
                )

    logging.info(f"{task} finished")


def demo(translater: Optional[Translater] = None, **config):
    # TODO: use config
    data_collector = []
    data_collector_web = []

    keywords = config["kv"]
    max_results = config["max_results"]
    publish_readme = config["publish_readme"]
    publish_gitpage = config["publish_gitpage"]

    b_update = config["update_paper_links"]
    logging.info(f"Update Paper Link = {b_update}")
    if config["update_paper_links"] == False:
        logging.info(f"GET daily papers begin")
        for topic, keyword in keywords.items():
            logging.info(f"topic: {topic}, keyword: {keyword}")
            data, data_web = get_daily_papers(
                topic, query=keyword, max_results=max_results, translater=translater
            )
            data_collector.append(data)
            data_collector_web.append(data_web)
            print("\n")
        logging.info(f"GET daily papers end")

    # 1. update README.md file
    if publish_readme:
        json_file = config["json_readme_path"]
        md_file = config["md_readme_path"]
        # update paper links
        if config["update_paper_links"]:
            update_paper_links(json_file)
        else:
            # update json data
            update_json_file(json_file, data_collector)
        # json data to markdown
        json_to_md(json_file, md_file, task="Update Readme")

    # 2. update docs/index.md file (to gitpage)
    if publish_gitpage:
        json_file = config["json_gitpage_path"]
        md_file = config["md_gitpage_path"]
        # TODO: duplicated update paper links!!!
        if config["update_paper_links"]:
            update_paper_links(json_file)
        else:
            update_json_file(json_file, data_collector)
        json_to_md(
            json_file,
            md_file,
            task="Update GitPage",
            to_web=True,
            use_tc=False,
            use_b2t=False,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config_path", type=str, default="config.yaml", help="configuration file path"
    )
    parser.add_argument(
        "--update_paper_links",
        default=False,
        action="store_true",
        help="whether to update paper links etc.",
    )
    parser.add_argument(
        "--google_api_key", type=str, default="", help="google ai api key."
    )
    args = parser.parse_args()
    config = load_config(args.config_path)
    # 覆盖从配置文件中读取的关键词，不采用从配置文件读取，而是直接写死
    #  This should be unencoded. Use `au:del_maestro AND ti:checkerboard`, not `au:del_maestro+AND+ti:checkerboard`.
    config["kv"] = {
        "多模态": 'abs:("Multi-modal Models" OR "Multimodal Model" OR LMMs OR "vision-language model"OR "Vision Language Models" OR VLMs \
        "Vision-and-Language Pre-training" OR VLP OR "Multimodal Learning" OR "multimodal pretraining" OR MLLM)',
        "6DOF Object Pose": 'abs:("Object Pose Estimation" OR "object 6D pose estimation")',
        "nerf": 'abs:("Radiance Fields")',
        "分类/检测/识别/分割": 'abs:("image classification" OR "object detection" OR "super resolution" OR "Object Tracking")',
        "模型压缩/优化": 'abs:("Network Architecture Search" OR "Knowledge Distillation" OR "model optimizer")',
        "OCR": 'abs:("optical character recognition" OR ocr)',
        "生成模型": 'abs:("diffusion model" OR "text-to-video synthesis" OR T2V OR "generative model")',
        "LLM": 'abs:("state-of-the-art LLMs" OR "training language models")',
        "Transformer": 'abs:(self-attention OR cross-attention OR "cross attention")',
        "3DGS": 'abs:("3d gaussian splatting" OR "gaussian splatting")',
        "3D/CG": 'abs:("3D detection" OR "3D reconstruction" OR "3D understanding")',
        "各类学习方式": 'abs:(Semi-supervised OR unsupervised OR "Continual Learning" OR "Incremental Learning" OR "Contrastive Learning")',
    }

    config = {**config, "update_paper_links": args.update_paper_links}
    if args.google_api_key:
        api = args.google_api_key
        translater = Translater(api_key=api)
        demo(translater, **config)
    else:
        demo(**config)
