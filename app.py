import os
import hashlib
import markdown
import bleach
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Role, Book, Genre, Cover, Review, book_genre
from forms import BookForm, ReviewForm, LoginForm

# ---------- Инициализация ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkeychangeinproduction'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  

# Создаём папку для загрузок, если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Для выполнения данного действия необходимо пройти процедуру аутентификации'

# ---------- Вспомогательные функции ----------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'jpg', 'jpeg', 'png', 'gif'}

def compute_md5(file_data):
    return hashlib.md5(file_data).hexdigest()

def save_cover_file(file_data, md5_hash):
    """Сохраняет файл на диск, имя = md5_hash + расширение"""
    ext = file_data.filename.rsplit('.', 1)[1].lower()
    filename = f"{md5_hash}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_data.save(filepath)
    return filename

def render_markdown(text):
    """Преобразует Markdown в HTML и чистит опасные теги"""
    html = markdown.markdown(text, extensions=['extra'])
    clean_html = bleach.clean(html, tags=['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'code', 'pre', 'a'], attributes={'a': ['href', 'title']})
    return clean_html

def get_avg_rating(book_id):
    reviews = Review.query.filter_by(book_id=book_id).all()
    if not reviews:
        return 0
    return round(sum(r.rating for r in reviews) / len(reviews), 1)

def get_reviews_count(book_id):
    return Review.query.filter_by(book_id=book_id).count()

# ---------- Загрузка пользователя для Flask-Login ----------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------- Контекстный процессор для передачи ролей и фио в шаблоны ----------
@app.context_processor
def utility_processor():
    def user_fullname():
        if current_user.is_authenticated:
            return f"{current_user.surname} {current_user.name} {current_user.patronymic or ''}".strip()
        return ''
    return dict(user_fullname=user_fullname, current_user=current_user)



# ---------- Маршруты ----------
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Поиск
    search_title = request.args.get('title', '').strip()
    search_genres = request.args.getlist('genres')  # список id
    search_years = request.args.getlist('years')    # список строк годов
    search_pages_from = request.args.get('pages_from', '', type=str)
    search_pages_to = request.args.get('pages_to', '', type=str)
    search_author = request.args.get('author', '').strip()

    query = Book.query

    if search_title:
        query = query.filter(Book.title.ilike(f'%{search_title}%'))
    if search_author:
        query = query.filter(Book.author.ilike(f'%{search_author}%'))
    if search_genres:
        # Фильтр по жанрам: книга должна содержать все выбранные жанры
        for gid in search_genres:
            query = query.filter(Book.genres.any(Genre.id == int(gid)))
    if search_years:
        years_int = [int(y) for y in search_years if y.isdigit()]
        if years_int:
            query = query.filter(Book.year.in_(years_int))
    # Объём от/до
    if search_pages_from and search_pages_from.isdigit():
        query = query.filter(Book.pages >= int(search_pages_from))
    if search_pages_to and search_pages_to.isdigit():
        query = query.filter(Book.pages <= int(search_pages_to))

    # Сортировка по году (сначала новые)
    query = query.order_by(Book.year.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    books = pagination.items

    # Данные для фильтров: все жанры, уникальные годы из БД
    all_genres = Genre.query.order_by(Genre.name).all()
    all_years = db.session.query(Book.year).distinct().order_by(Book.year.desc()).all()
    all_years = [str(y[0]) for y in all_years]

    # Подготовка данных для книг: средняя оценка, количество рецензий
    books_data = []
    for book in books:
        books_data.append({
            'book': book,
            'avg_rating': get_avg_rating(book.id),
            'reviews_count': get_reviews_count(book.id)
        })
    
    search_params_for_pagination = {k: v for k, v in request.args.items() if k != 'page'}

    return render_template('index.html',
                       books_data=books_data,
                       pagination=pagination,
                       all_genres=all_genres,
                       all_years=all_years,
                       search_params=request.args, 
                       search_params_for_pagination=search_params_for_pagination) 


@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    cover = book.cover
    reviews = Review.query.filter_by(book_id=book_id).order_by(Review.created_at.desc()).all()
    # Преобразуем описание книги из Markdown
    book_description_html = render_markdown(book.description)
    # Для рецензий
    for rev in reviews:
        rev.text_html = render_markdown(rev.text)
    user_review = None
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    return render_template('book_detail.html', book=book, cover=cover, reviews=reviews,
                           book_description_html=book_description_html, user_review=user_review)

@app.route('/book/add', methods=['GET', 'POST'])
@login_required
def add_book():
    if current_user.role.name not in ['admin', 'moderator']:
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    form = BookForm()
    # Заполняем choices для жанров
    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]
    if form.validate_on_submit():
        # Санитайзинг описания
        clean_description = bleach.clean(form.description.data, strip=True)
        # Начинаем транзакцию
        try:
            # 1. Создаём книгу (без обложки)
            book = Book(
                title=form.title.data,
                description=clean_description,
                year=form.year.data,
                publisher=form.publisher.data,
                author=form.author.data,
                pages=form.pages.data
            )
            db.session.add(book)
            db.session.flush()  # чтобы получить book.id

            # 2. Жанры
            selected_genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
            book.genres = selected_genres

            # 3. Обложка
            cover_file = form.cover.data
            if cover_file and allowed_file(cover_file.filename):
                file_data = cover_file.read()
                md5_hash = compute_md5(file_data)
                # Проверяем, есть ли уже такое изображение
                existing_cover = Cover.query.filter_by(md5_hash=md5_hash).first()
                if existing_cover:
                    # Используем существующий файл (но проверяем, что файл на диске есть)
                    cover_filename = existing_cover.filename
                    cover_mime = existing_cover.mime_type
                else:
                    # Сохраняем новый файл
                    cover_file.seek(0)
                    cover_filename = save_cover_file(cover_file, md5_hash)
                    cover_mime = cover_file.mimetype
                    # Добавляем запись в Cover
                    new_cover = Cover(
                        filename=cover_filename,
                        mime_type=cover_mime,
                        md5_hash=md5_hash,
                        book_id=book.id
                    )
                    db.session.add(new_cover)
                # Если использовали существующую обложку, нужно связать её с книгой
                if existing_cover:
                    existing_cover.book_id = book.id
                db.session.commit()
                flash('Книга успешно добавлена', 'success')
                return redirect(url_for('book_detail', book_id=book.id))
            else:
                db.session.rollback()
                flash('Необходимо загрузить обложку (jpg, png, gif)', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'При сохранении данных возникла ошибка: {str(e)}', 'danger')
    return render_template('book_form.html', form=form, title='Добавление книги')

@app.route('/book/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    if current_user.role.name not in ['admin', 'moderator']:
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    form = BookForm()
    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]
    if form.validate_on_submit():
        clean_description = bleach.clean(form.description.data, strip=True)
        try:
            book.title = form.title.data
            book.description = clean_description
            book.year = form.year.data
            book.publisher = form.publisher.data
            book.author = form.author.data
            book.pages = form.pages.data
            selected_genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
            book.genres = selected_genres
            # Обложка не редактируется
            db.session.commit()
            flash('Книга успешно обновлена', 'success')
            return redirect(url_for('book_detail', book_id=book.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении: {str(e)}', 'danger')
    else:
        # Заполняем форму текущими данными
        form.title.data = book.title
        form.description.data = book.description
        form.year.data = book.year
        form.publisher.data = book.publisher
        form.author.data = book.author
        form.pages.data = book.pages
        form.genres.data = [g.id for g in book.genres]
    return render_template('book_form.html', form=form, title='Редактирование книги', is_edit=True)

@app.route('/book/<int:book_id>/delete', methods=['POST'])
@login_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    if current_user.role.name != 'admin':
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    # Проверяем, используется ли файл обложки другими книгами
    cover = book.cover
    if cover:
        # Ищем другие книги с таким же md5_hash
        other_covers = Cover.query.filter(Cover.md5_hash == cover.md5_hash, Cover.book_id != book.id).count()
        if other_covers == 0:
            # Удаляем файл
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], cover.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
    db.session.delete(book)
    db.session.commit()
    flash('Книга успешно удалена', 'success')
    return redirect(url_for('index'))

@app.route('/book/<int:book_id>/review/new', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    book = Book.query.get_or_404(book_id)
    # Проверяем, не писал ли пользователь уже рецензию
    existing_review = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    if existing_review:
        flash('Вы уже оставляли рецензию на эту книгу', 'warning')
        return redirect(url_for('book_detail', book_id=book_id))
    form = ReviewForm()
    if form.validate_on_submit():
        clean_text = bleach.clean(form.text.data, strip=True)
        try:
            review = Review(
                book_id=book_id,
                user_id=current_user.id,
                rating=form.rating.data,
                text=clean_text
            )
            db.session.add(review)
            db.session.commit()
            flash('Рецензия сохранена', 'success')
            return redirect(url_for('book_detail', book_id=book_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении рецензии: {str(e)}', 'danger')
    return render_template('review_form.html', form=form, book=book)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(login=form.login.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Невозможно аутентифицироваться с указанными логином и паролем', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def get_cover(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/review/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    book = review.book
    
    if current_user.role.name not in ['admin', 'moderator']:
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('book_detail', book_id=book.id))
    
    db.session.delete(review)
    db.session.commit()
    flash('Рецензия удалена', 'success')
    return redirect(url_for('book_detail', book_id=book.id))

if __name__ == '__main__':
    app.run(debug=True)