import base64
import io
import json
import mimetypes
import urllib.error
import urllib.request
from pathlib import Path


OPENROUTER_CHAT_COMPLETIONS_URL = 'https://openrouter.ai/api/v1/chat/completions'
DEFAULT_OPENROUTER_MODEL = 'openai/gpt-4o-2024-08-06'


MENU_CORRECTION_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'items': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'name': {'type': 'string'},
                    'price': {'type': 'integer', 'minimum': 0, 'maximum': 9999},
                    'size': {'type': 'string'},
                    'category': {'type': 'string'},
                    'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                    'source_reason': {'type': 'string'},
                },
                'required': ['name', 'price', 'size', 'category', 'confidence', 'source_reason'],
            },
        },
        'rejected_texts': {
            'type': 'array',
            'items': {'type': 'string'},
        },
    },
    'required': ['items', 'rejected_texts'],
}


def _default_http_post(url, headers, payload, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={**headers, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'OpenRouter API request failed: {exc.code} {detail}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'OpenRouter API request failed: {exc.reason}') from exc


def _image_data_url(image_path, max_side=None):
    path = Path(image_path)
    if max_side:
        from PIL import Image, ImageOps

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            if max(image.size) > max_side:
                image.thumbnail((max_side, max_side))
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=88, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
        mime_type = 'image/jpeg'
    else:
        mime_type = mimetypes.guess_type(path.name)[0] or 'image/jpeg'
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def normalize_ai_menu_item(item):
    name = str(item.get('name') or '').strip()
    size = item.get('size')
    if isinstance(size, str):
        size = size.strip() or None
    if size and not name.upper().endswith(f' {size}'.upper()):
        name = f'{name} {size}'.strip()

    try:
        price = int(item.get('price'))
    except (TypeError, ValueError) as exc:
        raise ValueError('AI response did not contain valid menu items') from exc

    if not name or price < 0 or price > 9999:
        raise ValueError('AI response did not contain valid menu items')

    confidence = item.get('confidence', 0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0
    confidence = min(1, max(0, confidence))

    category = item.get('category')
    if isinstance(category, str):
        category = category.strip() or None

    return {
        'name': name,
        'price': price,
        'size': size,
        'category': category,
        'confidence': confidence,
        'source_reason': str(item.get('source_reason') or '').strip(),
    }


def parse_openrouter_menu_response(response):
    try:
        content = response['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError('OpenRouter response did not include message content') from exc

    if isinstance(content, list):
        text_parts = [
            part.get('text', '')
            for part in content
            if isinstance(part, dict) and part.get('type') in ('text', 'output_text')
        ]
        content = ''.join(text_parts)

    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('OpenRouter response was not valid JSON') from exc

    items = [normalize_ai_menu_item(item) for item in parsed.get('items', [])]
    if not items:
        raise ValueError('AI response did not contain valid menu items')

    return {
        'items': items,
        'rejected_texts': [str(text) for text in parsed.get('rejected_texts', []) if str(text).strip()],
    }


class OpenRouterMenuCorrectionClient:
    def __init__(
        self,
        api_key,
        model=DEFAULT_OPENROUTER_MODEL,
        site_url=None,
        site_name=None,
        http_post=None,
        timeout=60,
        image_max_side=None,
    ):
        self.api_key = api_key
        self.model = model or DEFAULT_OPENROUTER_MODEL
        self.site_url = site_url
        self.site_name = site_name
        self.http_post = http_post or _default_http_post
        self.timeout = timeout
        self.image_max_side = image_max_side

    def correct_menu(self, image_path, ocr_boxes, candidates, session_title):
        if not self.api_key:
            raise RuntimeError('OPENROUTER_API_KEY is not configured')

        payload = {
            'model': self.model,
            'provider': {'require_parameters': True},
            'messages': [{
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': (
                            '你是台灣飲料菜單資料校正助手。請根據圖片、OCR boxes 與候選品項，'
                            '只輸出真正可下單的飲料品項與價格。排除促銷標題、分類標題、'
                            '店家資訊、加料清單、容量標示、月份、冷熱/甜度說明。'
                            f'\n場次：{session_title}'
                            f'\nOCR boxes JSON：{json.dumps(ocr_boxes, ensure_ascii=False)}'
                            f'\n候選品項 JSON：{json.dumps(candidates, ensure_ascii=False)}'
                        ),
                    },
                    {
                        'type': 'image_url',
                        'image_url': {'url': _image_data_url(image_path, max_side=self.image_max_side)},
                    },
                ],
            }],
            'response_format': {
                'type': 'json_schema',
                'json_schema': {
                    'name': 'drink_menu_correction',
                    'strict': True,
                    'schema': MENU_CORRECTION_SCHEMA,
                },
            },
        }
        headers = {'Authorization': f'Bearer {self.api_key}'}
        if self.site_url:
            headers['HTTP-Referer'] = self.site_url
        if self.site_name:
            headers['X-OpenRouter-Title'] = self.site_name

        try:
            response = self.http_post(OPENROUTER_CHAT_COMPLETIONS_URL, headers, payload, self.timeout)
        except urllib.error.URLError as exc:
            raise RuntimeError(f'OpenRouter API request failed: {exc.reason}') from exc
        return parse_openrouter_menu_response(response)
