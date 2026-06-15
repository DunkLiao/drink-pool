import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ENV_FILE = os.path.join(BASE_DIR, '.env')


def load_env_file(path=ENV_FILE):
    if not os.path.exists(path):
        return

    with open(path, encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env_file()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'drink-pool-secret-key-change-in-production')
    ADMIN_ENTRY_PASSWORD = os.environ.get('ADMIN_ENTRY_PASSWORD')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "db", "drink_pool.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'photos')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Sweetness & ice choices (hardcoded per source.txt convention)
    SWEETNESS_CHOICES = [
        ('無糖', '無糖'),
        ('微糖', '微糖'),
        ('半糖', '半糖'),
        ('少糖', '少糖'),
        ('正常糖', '正常糖'),
    ]
    ICE_CHOICES = [
        ('去冰', '去冰'),
        ('微冰', '微冰'),
        ('少冰', '少冰'),
        ('正常冰', '正常冰'),
        ('常溫', '常溫'),
        ('熱', '熱'),
    ]
    MAX_ADDONS = 5

    # Default site settings (can be overridden via admin panel)
    DEFAULT_SETTINGS = {
        'site_title': '飲料團購系統',
        'site_subtitle': '臺灣銀行 風險管理部 飲料團購系統',
        'org_name': '臺灣銀行',
        'org_dept': '風險管理部',
    }
