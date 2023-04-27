import os
import shutil
from io import BytesIO
from typing import Dict, List, Union
import random
import uuid
import arxiv
import re

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import urllib.parse as urlparse

import numpy as np
import openai
import replicate
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
FONTS_DIR = os.path.join(ROOT_DIR, 'fonts')
OUTPUT_DIR = os.path.join(ROOT_DIR, 'output')

# set google api key
with open(os.path.join(ROOT_DIR, 'google.txt'), 'r') as f:
    os.environ["GOOGLE_API_KEY"] = f.read()
# set replicate api token
with open(os.path.join(ROOT_DIR, 'replicate.txt'), 'r') as f:
    os.environ['REPLICATE_API_TOKEN'] = f.read()
# set openai api token
with open(os.path.join(ROOT_DIR, 'openai.txt'), 'r') as f:
    _key = f.read()
    os.environ['OPENAI_API_KEY'] = _key
    openai.api_key = _key

def gpt_text(
        prompt: Union[str, List[Dict[str, str]]] = None,
        system: str = None,
        model: str = "gpt-3.5-turbo",
        temperature : float = 0.6,
        max_tokens: int = 32,
        stop: List[str] = ["\n"],
):
    if isinstance(prompt, str):
        prompt = [{"role" : "user", "content" : prompt}]
    elif prompt is None:
        prompt = []
    if system is not None:
        prompt = [{"role" : "system", "content" : system}] + prompt 
    response = openai.ChatCompletion.create(
        messages=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        stop=stop,
    )
    return response['choices'][0]['message']['content']

def gpt_color():
    try:
        color_name = gpt_text(
            system=' '.join([
                "You generate unique and interesting colors for a crayon set.",
                "Crayon color names are only a few words.", 
                "Respond with the colors only: no extra text or explanations.",
            ]),
            temperature=0.99,
        )
        rgb = gpt_text(
            prompt=color_name,
            system=' '.join([
                "You generate RGB color tuples for digital art based on word descriptions.",
                "Respond with three integers in the range 0 to 255 representing R, G, and B.",
                "The three integers should be separated by commas, without spaces.",
                "Respond with the colors only: no extra text or explanations.",
            ]),
            temperature=0.1,
        )
        rgb = rgb.split(',')
        assert len(rgb) == 3
        rgb = tuple([int(x) for x in rgb])
        assert all([0 <= x <= 256 for x in rgb])
    except:
        color_name = 'black'
        rgb = (0, 0, 0)
    return rgb, color_name

def gpt_image(
    prompt: str = None,
    n: int = 1,
    image_path = os.path.join(DATA_DIR, 'test.png'),
    output_path = os.path.join(OUTPUT_DIR, 'test.png'),
    image_size: str = "1024x1024",
):
    if prompt is None:
        response = openai.Image.create_variation(
            image=open(image_path, "rb"),
            n=n,
            size=image_size,
        )
        img_url = response['data'][0]['url']
    else:
        response = openai.Image.create(
            prompt=prompt,
            n=n,
            size=image_size,
        )
        img_url = response['data'][0]['url']
    # save output image
    image = Image.open(BytesIO(requests.get(img_url).content))
    image.save(output_path)


def remove_bg(
    image_path = os.path.join(DATA_DIR, 'test.png'),
    output_path = os.path.join(OUTPUT_DIR, 'test_nobg.png'),
):
    # use replicate api to remove background
    # need to have REPLICATE_API_KEY environment variable set
    img_url = replicate.run(
        "cjwbw/rembg:fb8af171cfa1616ddcf1242c093f9c46bcada5ad4cf6f2fbe8b81b330ec5c003",
        input={"image": open(image_path, "rb")}
    )
    # save output image
    image = Image.open(BytesIO(requests.get(img_url).content))
    image.save(output_path)

def draw_text(
    image_path = os.path.join(DATA_DIR, 'test.png'),
    output_path = os.path.join(OUTPUT_DIR, 'test_text.png'),
    text = 'Hello World',
    text_color = (255, 255, 255),
    font = 'Exo2-Bold',
    font_size = 72,
    rectangle_color = (0, 0, 0),
    rectangle_padding = 20,
):
    # choose file based on font name from font dir
    font_path = os.path.join(FONTS_DIR, font + '.ttf')
    font = ImageFont.truetype(font_path, font_size)
    # draw text on image
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    text_width, text_height = draw.textsize(text, font=font)
    # Calculate the position to center the text
    x = (image.size[0] - text_width) / 2
    y = (image.size[1] - text_height) / 2
    
    # Draw a solid colored rectangle behind the text
    rectangle_x1 = x - rectangle_padding
    rectangle_y1 = y - rectangle_padding
    rectangle_x2 = x + text_width + rectangle_padding
    rectangle_y2 = y + text_height + rectangle_padding
    draw.rectangle([rectangle_x1, rectangle_y1, rectangle_x2, rectangle_y2], fill=rectangle_color)
    
    # Render the text
    draw.text((x, y), text, fill=text_color, font=font)
    image.save(output_path)

def resize_bg(
    image_path = os.path.join(DATA_DIR, 'example_graphs.png'),
    output_path = os.path.join(OUTPUT_DIR, 'example_graphs_resized.png'),
    canvas_size = (1280, 720),
):
    img = Image.open(image_path)
    # Keep aspect ratio, resize width to fit
    width, height = img.size
    new_width = canvas_size[0]
    new_height = int(height * new_width / width)
    resized_image = img.resize((new_width, new_height), Image.ANTIALIAS)

    # Create a new canvas with the desired size, transparent background
    canvas = Image.new('RGBA', canvas_size, (0, 0, 0, 0))

    # Center the resized image on the canvas
    paste_position = (
        int((canvas_size[0] - new_width) / 2),
        int((canvas_size[1] - new_height) / 2),
    )
    canvas.paste(resized_image, paste_position)

    # Save the result
    canvas.save(output_path)

def stack_fgbg(
    fg_image_path = os.path.join(DATA_DIR, 'bu.1.1.nobg', 'test_bu_nobg.png'),
    bg_image_path = os.path.join(DATA_DIR, 'bg.16.9', 'test_bg.png'),
    output_path = os.path.join(OUTPUT_DIR, 'test_nobg.png'),
    # output image size,
    bg_size = (1280, 720),
    fg_size = (420, 420),
):
    # load images
    fg_image = Image.open(fg_image_path)
    bg_image = Image.open(bg_image_path)
    # resize images
    fg_image = fg_image.resize(fg_size)
    bg_image = bg_image.resize(bg_size)
    # Upper left corner of the foreground such that it sits in the lower left corner of background
    x = 0
    y = bg_size[1] - fg_size[1]
    # Final image
    fg_image_full = Image.new("RGBA", bg_size)
    fg_image_full.paste(fg_image, (x, y), fg_image)
    final = Image.alpha_composite(bg_image, fg_image_full)
    # paste images, account for alpha channel
    # save output image
    final.save(output_path)

def get_video_info(video_id):
    if not video_id:
        return None
    try:
        youtube = build('youtube', 'v3', developerKey=os.environ["GOOGLE_API_KEY"])
        response = youtube.videos().list(
            part='snippet',
            id=video_id
        ).execute()
        if 'items' in response and len(response['items']) > 0:
            description = response['items'][0]['snippet']['description']
            title = response['items'][0]['snippet']['title']
            return title, description
        else:
            return None
    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred: {e.content}")
        return None

def get_video_hashtags_from_description(description):
    # The last line of the description is the hashtags
    hashtags = description.splitlines()[-1]
    return hashtags

def get_video_sentence_from_description(description):
    # Split the text by the "Like" section
    parts = description.split("Like 👍.")

    # Get everything before the "Like" section
    text_before_like = parts[0].strip()
    return text_before_like

def generate_thumbnails(
        input_image_path: str,
        output_tmp_dir: str,
        output_dir: str,
        title: str,
):
    fg_prompt = gpt_text(
        prompt="portrait of white bengal cat, blue eyes, cute, chubby",
        system=' '.join([
        "You generate variations of string prompts for image generation.",
        "Respond with a single new variant of the user prompt. ",
        "Add several new interesting or related words.",
        "Respond with the prompt only: no extra text or explanations.",
    ]),
    )

    # Foreground image remove background
    fg_img_name = str(uuid.uuid4())
    gpt_image(
        prompt=fg_prompt,
        output_path=os.path.join(output_tmp_dir, f'{fg_img_name}.png'),
        image_size="512x512",
    )
    remove_bg(
        image_path=os.path.join(output_tmp_dir, f'{fg_img_name}.png'),
        output_path=os.path.join(output_tmp_dir, f'{fg_img_name}_nobg.png'),
    )

    # Background image 
    bg_img_name = str(uuid.uuid4())
    resize_bg(
        image_path = input_image_path,
        output_path = os.path.join(output_tmp_dir, f'{bg_img_name}.png'),
        canvas_size = (1280, 720),
    )

    text_rgb, text_color = gpt_color()
    rect_rgb, rect_color = gpt_color()

    # Write text on top of image
    draw_text(
        image_path = os.path.join(output_tmp_dir, f'{bg_img_name}.png'),
        output_path = os.path.join(output_tmp_dir,  f'{bg_img_name}_text.png'),
        text = title,
        text_color = text_rgb,
        font_size = 60,
        rectangle_color = rect_rgb,
        rectangle_padding = 20,
    )

    # Stack foreground and background
    combo_image_name = str(uuid.uuid4())
    stack_fgbg(
        fg_image_path = os.path.join(output_tmp_dir, f'{fg_img_name}_nobg.png'),
        bg_image_path = os.path.join(output_tmp_dir, f'{bg_img_name}_text.png'),
        output_path = os.path.join(output_dir, f'{combo_image_name}.png'),
        bg_size = (1280, 720),
        fg_size = (420, 420),
    )

def generate_yttext(
    output_path: str,
    desired_sentence: str,
    example_video_ids: List[str],
):

    socials = '''
Like 👍. Comment 💬. Subscribe 🟥.

⌨️ GitHub
https://github.com/hu-po

🗨️ Discord
https://discord.gg/XKgVSxB6dE

📸 Instagram
http://instagram.com/gnocchibengal
    '''

    best_videos = []
    for video_id in example_video_ids:
        title, description = get_video_info(video_id)
        hashtags = get_video_hashtags_from_description(description)
        sentence = get_video_sentence_from_description(description)
        best_videos.append({
            "title": title,
            "hashtags": hashtags,
            "sentence": sentence,
        })

    in_context_titles = []
    for best_video in best_videos:
        in_context_titles += [{
            "role": "user",
            "content": best_video["sentence"]
        }]
        in_context_titles += [{
            "role": "assistant",
            "content": best_video["title"],
        }]
    # Add the last part of the prompt
    in_context_titles += [{
        "role": "user",
        "content": desired_sentence,
    }]
    title = gpt_text(
        prompt=in_context_titles,
        system=' '.join([
            "You create titles for YouTube videos.",
            "Respond with the title that best fits the description provided by the user.",
            "Respond with the title only: no extra text or explanations.",
        ]),
        temperature=0.6,
    )
    

    in_context_hashtags = []
    for best_video in best_videos:
        in_context_hashtags += [{
            "role": "user",
            "content": best_video["sentence"]
        }]
        in_context_hashtags += [{
            "role": "assistant",
            "content": best_video["hashtags"],
        }]
    # Add the last part of the prompt
    in_context_hashtags += [{
        "role": "user",
        "content": desired_sentence,
    }]
    hashtags = gpt_text(
        prompt=in_context_hashtags,
        system=' '.join([
            "You create hashtags for YouTube videos.",
            "Respond with up to 4 hashtags that match the user prompt.",
            "Respond with the hashtags only: no extra text or explanations.",
        ]),
        temperature=0.6,
    )

    # Combine all the parts together
    full_description = f'{title}\n{desired_sentence}\n{socials}\n{hashtags}'

    # Save the description
    description_path = os.path.join(output_path, f'{str(uuid.uuid4())}.txt')
    with open(description_path, 'w') as f:
        f.write(full_description)

    return title

def get_arxiv_info(url):
    pattern = r'arxiv.org\/(?:abs|pdf)\/([\w.-]+)'
    match = re.search(pattern, url)

    if match:
        arxiv_id = match.group(1)
        search = arxiv.Search(id_list=[arxiv_id])
        paper = next(search.results())
        return paper
    else:
        return None
