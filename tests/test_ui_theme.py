from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_theme_tokens_use_requested_palette():
    css = read_text('static/css/style.css')

    assert '--color-bg: #FFFFFF' in css
    assert '--color-text: #424242' in css
    assert '--color-heading: #212121' in css
    assert '--color-primary: #B2DFDB' in css
    assert '--color-secondary: #F8BBD0' in css


def test_base_navbar_uses_light_custom_theme():
    base_html = read_text('templates/base.html')

    assert 'navbar-light app-navbar' in base_html
    assert 'navbar-dark bg-primary' not in base_html


def test_primary_card_headers_no_longer_depend_on_bootstrap_blue():
    template_paths = [
        'templates/order_form.html',
        'templates/admin/session_form.html',
        'templates/admin/settings.html',
        'templates/admin/entry.html',
        'templates/admin/login.html',
        'templates/admin/register.html',
    ]

    for path in template_paths:
        template = read_text(path)
        assert 'bg-primary text-white' not in template
