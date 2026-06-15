from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, IntegerField, SelectMultipleField, SelectField, PasswordField, BooleanField
from wtforms.validators import DataRequired, NumberRange, Optional

class BookForm(FlaskForm):
    title = StringField('Название', validators=[DataRequired()])
    description = TextAreaField('Описание (Markdown)', validators=[DataRequired()])
    year = IntegerField('Год', validators=[DataRequired(), NumberRange(min=0, max=2100)])
    publisher = StringField('Издательство', validators=[DataRequired()])
    author = StringField('Автор', validators=[DataRequired()])
    pages = IntegerField('Объём (страниц)', validators=[DataRequired(), NumberRange(min=1)])
    genres = SelectMultipleField('Жанры', coerce=int, validators=[DataRequired()])
    cover = FileField('Обложка', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg', 'gif'], 'Только изображения!')])

class ReviewForm(FlaskForm):
    rating = SelectField('Оценка', choices=[
        (5, '5 – отлично'),
        (4, '4 – хорошо'),
        (3, '3 – удовлетворительно'),
        (2, '2 – неудовлетворительно'),
        (1, '1 – плохо'),
        (0, '0 – ужасно')
    ], coerce=int, validators=[DataRequired()])
    text = TextAreaField('Текст рецензии (Markdown)', validators=[DataRequired()])

class LoginForm(FlaskForm):
    login = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember = BooleanField('Запомнить меня')