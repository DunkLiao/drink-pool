from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import IntegerField, StringField, PasswordField, SelectField, TextAreaField, DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, NumberRange, Optional


class LoginForm(FlaskForm):
    username = StringField('帳號', validators=[DataRequired(message='請輸入帳號')])
    password = PasswordField('密碼', validators=[DataRequired(message='請輸入密碼')])
    submit = SubmitField('登入')


class AdminEntryPasswordForm(FlaskForm):
    password = PasswordField('後台入口密碼', validators=[DataRequired(message='請輸入後台入口密碼')])
    submit = SubmitField('進入後台登入')


class RegisterForm(FlaskForm):
    username = StringField('帳號', validators=[
        DataRequired(message='請輸入帳號'),
        Length(min=3, max=80, message='帳號長度需為 3-80 字元'),
    ])
    password = PasswordField('密碼', validators=[
        DataRequired(message='請輸入密碼'),
        Length(min=6, message='密碼長度至少 6 字元'),
    ])
    confirm_password = PasswordField('確認密碼', validators=[
        DataRequired(message='請再次輸入密碼'),
        EqualTo('password', message='兩次密碼輸入不一致'),
    ])
    submit = SubmitField('註冊')


class SessionForm(FlaskForm):
    title = StringField('團購名稱', validators=[DataRequired(message='請輸入團購名稱')])
    photo = FileField('訂單照片', validators=[
        FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp'], '僅允許圖片格式 (png, jpg, jpeg, gif, webp)'),
        Optional(),
    ])
    start_time = DateTimeLocalField('開始時間', validators=[DataRequired(message='請選擇開始時間')], format='%Y-%m-%dT%H:%M')
    end_time = DateTimeLocalField('結束時間', validators=[DataRequired(message='請選擇結束時間')], format='%Y-%m-%dT%H:%M')
    submit = SubmitField('儲存')


class DepartmentForm(FlaskForm):
    name = StringField('科別名稱', validators=[DataRequired(message='請輸入科別名稱'), Length(max=100)])
    submit = SubmitField('新增')


class MenuItemForm(FlaskForm):
    name = StringField('品項名稱', validators=[DataRequired(message='請輸入品項名稱'), Length(max=200)])
    price = IntegerField('價格', validators=[
        DataRequired(message='請輸入價格'),
        NumberRange(min=0, max=9999, message='價格需介於 0 到 9999'),
    ])
    submit = SubmitField('新增品項')


class OrderForm(FlaskForm):
    name = StringField('姓名', validators=[DataRequired(message='請輸入姓名'), Length(max=100)])
    department = SelectField('科別', coerce=int, validators=[DataRequired(message='請選擇科別')])
    drink_item = StringField('飲料品項', validators=[DataRequired(message='請輸入飲料品項'), Length(max=200)])
    sweetness = SelectField('甜度', validators=[DataRequired(message='請選擇甜度')])
    ice = SelectField('冰塊', validators=[DataRequired(message='請選擇冰塊')])
    notes = TextAreaField('備註', validators=[Optional(), Length(max=500)])
    submit = SubmitField('送出訂單')


class SettingsForm(FlaskForm):
    site_title = StringField('網站標題', validators=[DataRequired(message='請輸入網站標題'), Length(max=200)])
    site_subtitle = StringField('頁腳文字', validators=[DataRequired(message='請輸入頁腳文字'), Length(max=200)])
    org_name = StringField('組織名稱', validators=[DataRequired(message='請輸入組織名稱'), Length(max=100)])
    org_dept = StringField('部門名稱', validators=[DataRequired(message='請輸入部門名稱'), Length(max=100)])
    submit = SubmitField('儲存設定')
