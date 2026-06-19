import os
import re
import tempfile


_OCR_CACHE = {}


PRICE_PATTERN = re.compile(r'^(?P<name>.+?)\s*(?:NT\$|\$)?\s*(?P<price>\d{1,4})\s*$')
MULTI_PRICE_PATTERN = re.compile(r'^(?P<name>.+?)\s+(?P<prices>(?:\d{1,4}\s+){1,3}\d{1,4})\s*$')
PRICE_TOKEN_PATTERN = re.compile(r'^(?:NT\$|\$)?(?P<price>\d{1,4})$')
NOISE_PATTERN = re.compile(
    r'(TEL|電話|地址|QR|LINE|官方|門市|加入會員|糖量|冰量|外送|自取|優惠|推薦|Recommend|'
    r'登場價|甜度固定|產品略含甜度|加好加滿|加料區|oz|OZ)',
    re.IGNORECASE,
)
NON_ITEM_PATTERN = re.compile(
    r'^(?:冷|熱|冷/熱|冷/熟|冰沙|碎冰沙|細冰沙|[ML]|L|M|瓶|1瓶|\d{1,2}[-~]\d{1,2}月)$',
    re.IGNORECASE,
)


def normalize_menu_name(name):
    return re.sub(r'\s+', '', name or '').strip().lower()


def clean_menu_name(name):
    cleaned = re.sub(r'[•●▣□☑✓✔★☆👍#]+', '', name or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ：:-\t')
    return cleaned


def is_noise_text(text):
    if not text:
        return True
    stripped = text.strip()
    if NOISE_PATTERN.search(stripped):
        return True
    if NON_ITEM_PATTERN.match(stripped):
        return True
    if len(stripped) <= 1 and not re.search(r'[\u4e00-\u9fff]', stripped):
        return True
    return False


def build_menu_item_variants(name, prices, confidence=None):
    cleaned_name = clean_menu_name(name)
    if not cleaned_name or is_noise_text(cleaned_name):
        return []
    if len(prices) == 1:
        suffixes = ['']
    elif len(prices) == 2:
        suffixes = ['M', 'L']
    else:
        suffixes = [str(i + 1) for i in range(len(prices))]

    items = []
    for suffix, price in zip(suffixes, prices):
        item_name = f'{cleaned_name} {suffix}'.strip()
        items.append({'name': item_name, 'price': int(price), 'ocr_confidence': confidence})
    return items


def parse_menu_items_from_text(text):
    seen = set()
    items = []
    for raw_line in (text or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        multi_match = MULTI_PRICE_PATTERN.match(line)
        if multi_match:
            name = multi_match.group('name')
            prices = [int(price) for price in multi_match.group('prices').split()]
        else:
            match = PRICE_PATTERN.match(line)
            if not match:
                continue
            name = match.group('name')
            prices = [int(match.group('price'))]

        for item in build_menu_item_variants(name, prices):
            normalized = normalize_menu_name(item['name'])
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            items.append(item)
    return items


def parse_menu_items_from_boxes(boxes, row_tolerance=18):
    normalized_boxes = []
    for box in boxes or []:
        text = str(box.get('text', '')).strip()
        if not text:
            continue
        x = float(box.get('x', 0))
        y = float(box.get('y', 0))
        width = float(box.get('width', 0))
        height = float(box.get('height', 0))
        normalized_boxes.append({
            'text': text,
            'x': x,
            'y': y,
            'cx': x + width / 2,
            'cy': y + height / 2,
            'width': width,
            'height': height,
            'score': box.get('score'),
        })

    price_boxes = []
    name_boxes = []
    for box in normalized_boxes:
        price_match = PRICE_TOKEN_PATTERN.match(box['text'])
        if price_match:
            price_boxes.append({**box, 'price': int(price_match.group('price'))})
        elif re.search(r'[\u4e00-\u9fff]', box['text']) and not is_noise_text(box['text']):
            name_boxes.append(box)

    seen = set()
    items = []
    for name_box in sorted(name_boxes, key=lambda item: (item['y'], item['x'])):
        row_prices = [
            price_box for price_box in price_boxes
            if price_box['cx'] > name_box['cx']
            and abs(price_box['cy'] - name_box['cy']) <= max(row_tolerance, name_box['height'])
        ]
        row_prices = sorted(row_prices, key=lambda item: item['x'])[:2]
        if not row_prices:
            continue
        confidence = name_box.get('score')
        for item in build_menu_item_variants(name_box['text'], [price_box['price'] for price_box in row_prices], confidence):
            normalized = normalize_menu_name(item['name'])
            if normalized in seen:
                continue
            seen.add(normalized)
            items.append(item)
    return items


def get_paddle_ocr(lang='chinese_cht', factory=None):
    cache_key = lang
    if cache_key in _OCR_CACHE:
        return _OCR_CACHE[cache_key]

    if factory is None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError('尚未安裝 PaddleOCR，請先安裝 paddleocr 與 paddlepaddle。') from exc
        factory = PaddleOCR

    try:
        ocr = factory(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        ocr = factory(lang=lang)

    _OCR_CACHE[cache_key] = ocr
    return ocr


def preprocess_menu_image(image_path, max_side=2000):
    from PIL import Image, ImageOps

    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        if max(image.size) <= max_side:
            suffix = os.path.splitext(image_path)[1] or '.jpg'
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            image.save(temp_path, quality=92)
            return temp_path

        image.thumbnail((max_side, max_side))
        fd, temp_path = tempfile.mkstemp(suffix='.jpg')
        os.close(fd)
        image.save(temp_path, quality=92)
        return temp_path


def _flatten_paddle_result(result):
    lines = []

    def visit(node):
        if isinstance(node, dict):
            text = node.get('text') or node.get('rec_text')
            score = node.get('score') or node.get('rec_score')
            if text:
                lines.append((str(text), score))
            for value in node.values():
                visit(value)
            return
        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and isinstance(node[1], (list, tuple)) and node[1]:
                text = node[1][0]
                score = node[1][1] if len(node[1]) > 1 else None
                if isinstance(text, str):
                    lines.append((text, score))
                    return
            for value in node:
                visit(value)

    visit(result)
    return lines


def _box_from_poly(poly):
    xs = []
    ys = []
    if poly is None:
        return None
    for point in poly:
        if hasattr(point, '__len__') and len(point) >= 2:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if not xs or not ys:
        return None
    min_x = min(xs)
    min_y = min(ys)
    return {
        'x': min_x,
        'y': min_y,
        'width': max(xs) - min_x,
        'height': max(ys) - min_y,
    }


def _extract_paddle_boxes(result):
    boxes = []

    def first_present(mapping, keys):
        for key in keys:
            if key in mapping and mapping[key] is not None:
                return mapping[key]
        return None

    def add_box(text, score, poly):
        box = _box_from_poly(poly)
        if not box or not text:
            return
        boxes.append({**box, 'text': str(text), 'score': score})

    def visit(node):
        if isinstance(node, dict):
            payload = node.get('res') if isinstance(node.get('res'), dict) else node
            texts = payload.get('rec_texts')
            scores = payload.get('rec_scores') if payload.get('rec_scores') is not None else [None] * len(texts or [])
            polys = first_present(payload, ('rec_polys', 'dt_polys', 'rec_boxes'))
            if texts is not None and polys is not None and len(texts) > 0 and len(polys) > 0:
                for text, score, poly in zip(texts, scores, polys):
                    if isinstance(poly, (list, tuple)) and len(poly) == 4 and all(isinstance(value, (int, float)) for value in poly):
                        x1, y1, x2, y2 = poly
                        boxes.append({
                            'text': str(text),
                            'score': score,
                            'x': float(x1),
                            'y': float(y1),
                            'width': float(x2) - float(x1),
                            'height': float(y2) - float(y1),
                        })
                    else:
                        add_box(text, score, poly)
                return
            text = payload.get('text') if payload.get('text') is not None else payload.get('rec_text')
            score = payload.get('score') if payload.get('score') is not None else payload.get('rec_score')
            poly = first_present(payload, ('points', 'poly', 'box'))
            add_box(text, score, poly)
            for value in payload.values():
                visit(value)
            return

        if hasattr(node, 'json'):
            payload = node.json
            visit(payload() if callable(payload) else payload)
            return

        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and isinstance(node[0], (list, tuple)) and isinstance(node[1], (list, tuple)) and node[1]:
                text = node[1][0]
                score = node[1][1] if len(node[1]) > 1 else None
                add_box(text, score, node[0])
                return
            for value in node:
                visit(value)

    visit(result)
    return boxes


def extract_menu_items_from_image(image_path):
    lang = os.environ.get('PADDLEOCR_LANG', 'chinese_cht')
    ocr = get_paddle_ocr(lang=lang)

    max_side = int(os.environ.get('PADDLEOCR_MENU_MAX_SIDE', '2000'))
    processed_path = preprocess_menu_image(image_path, max_side=max_side)
    try:
        if hasattr(ocr, 'predict'):
            result = ocr.predict(processed_path)
        elif hasattr(ocr, 'ocr'):
            result = ocr.ocr(processed_path, cls=True)
        else:
            raise RuntimeError('目前 PaddleOCR 版本不支援已知的 Python OCR 介面。')
    finally:
        if processed_path != image_path and os.path.exists(processed_path):
            os.remove(processed_path)

    text_boxes = _extract_paddle_boxes(result)
    if text_boxes:
        return parse_menu_items_from_boxes(text_boxes)

    text_lines = _flatten_paddle_result(result)
    parsed = parse_menu_items_from_text('\n'.join(text for text, _score in text_lines))
    confidence_by_name = {}
    for text, score in text_lines:
        match = PRICE_PATTERN.match(text.strip())
        if not match:
            continue
        confidence_by_name[normalize_menu_name(match.group('name'))] = score

    for item in parsed:
        item['ocr_confidence'] = confidence_by_name.get(normalize_menu_name(item['name']))
    return parsed


def extract_text_boxes_from_image(image_path):
    lang = os.environ.get('PADDLEOCR_LANG', 'chinese_cht')
    ocr = get_paddle_ocr(lang=lang)

    max_side = int(os.environ.get('PADDLEOCR_MENU_MAX_SIDE', '2000'))
    processed_path = preprocess_menu_image(image_path, max_side=max_side)
    try:
        if hasattr(ocr, 'predict'):
            result = ocr.predict(processed_path)
        elif hasattr(ocr, 'ocr'):
            result = ocr.ocr(processed_path, cls=True)
        else:
            raise RuntimeError('目前 PaddleOCR 版本不支援已知的 Python OCR 介面。')
    finally:
        if processed_path != image_path and os.path.exists(processed_path):
            os.remove(processed_path)

    return _extract_paddle_boxes(result)
