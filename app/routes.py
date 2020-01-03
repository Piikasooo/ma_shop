import io
from pathlib import Path

import psycopg2
from PIL import Image
from flask import render_template, request, redirect, url_for, flash, g, session, send_file, abort
from sqlalchemy.exc import IntegrityError

from app.config import DATABASE, basedir
from cart import cart
from comments import comments
from errors import errors
from marks import mark
from product_categories import product_categories
from products import products
from users import validation
from .forms import *
from .models import *
from .breadcrumb import breadcrumb
from .login import login_required


def save_image_and_thumbnail(image_data, product_id):
    """save image and image_thumbnail"""
    image = Image.open(image_data)
    rgb_im = image.convert('RGB')
    image_name = f"{product_id}.jpg"
    rgb_im.save(Path(basedir, app.config['UPLOAD_FOLDER'], image_name))
    rgb_im.thumbnail(app.config['THUMBNAIL_SIZE'])
    thumbnail_name = f"{product_id}_thumbnail.jpg"
    rgb_im.save(Path(basedir, app.config['UPLOAD_FOLDER'], thumbnail_name))


@app.before_request
def get_db():
    if not hasattr(g, 'db'):
        g.db = psycopg2.connect(**DATABASE)


@app.teardown_request
def close_db(error):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


@app.route('/image/<ln>')
def image(ln):
    sn = products.get_product_image(g.db, ln)
    return send_file(io.BytesIO(sn), mimetype='image/jpeg')


@app.route('/')
@breadcrumb('Home')
def index():
    return render_template("index.html")


@app.route('/product/product_description/<product_id>', methods=("GET", "POST"))
def show_product(product_id):
    form = MarkForm()
    avg_mark = mark.get_average(g.db, product_id)
    with g.db.cursor() as cursor:
        cursor.execute(f"select id, name, price, image from products where id = '{product_id}'")
        prod_data = cursor.fetchone()
        comment = ""
        if request.method == "POST":
            comment = request.form.get("comment", "")
            if 'user_id' not in session:
                flash("Please log in for leaving your comment")
                return redirect(url_for('login'))
            else:
                comments.add(g.db, product_id, session['id_user'], comment)
        return render_template("product_description.html", data=prod_data, comment=comment, avg_mark=avg_mark, form=form)


@app.route('/product/set_mark/<string:product_id>', methods=("GET", "POST"))
@login_required
def set_product_mark(product_id):
    if request.method == "POST":
        new_mark = request.form.get("mark", "")
        if 'user_id' not in session:
            flash("Please log in to leave your mark")
            return redirect(url_for('login'))
        else:
            mark = Mark(session['user_id'], product_id, new_mark)
            db.session.add(mark)
            db.session.commit()
            flash("Your mark has been added successfully")
        return redirect(f'/product/product_description/{product_id}')


@app.route('/product/add_to_cart/<product_id>', methods=("GET", "POST"))
@login_required
def add_to_cart(product_id):
    if request.method == "POST":
        cart.add(g.db, session["user_id"], product_id)
    return redirect(url_for("get_catalogue"))


@app.route('/cart', methods=("GET", "POST"))
@login_required
@breadcrumb('Cart')
def cart_call():
    cart_items = {}
    items_qty = 0
    total_amount = 0
    if request.method == "POST":
        cart.delete(g.db, int(session["user_id"]), int(request.form.get("delete_item", "")))
    for product_id in cart.get_all(g.db, int(session["user_id"])):
        if product_id not in cart_items:
            name, price = products.get_for_cart(g.db, product_id)
            cart_items[product_id] = {
                "product_id": product_id,
                "name": name,
                "price": price,
                "pieces": 1
            }
            cart_items[product_id]["amount"] = cart_items[product_id]["price"] * cart_items[product_id]["pieces"]
        else:
            cart_items[product_id]["pieces"] += 1
            cart_items[product_id]["amount"] += cart_items[product_id]["price"]
        total_amount += cart_items[product_id]["price"]
        items_qty += 1
    return render_template("cart.html", cart_items=cart_items, items_qty=items_qty, total_amount=total_amount)


@app.route('/news')
@breadcrumb('News')
def news():
    news = db.session.query(News) \
        .join(Users) \
        .add_columns(News.title, News.post, News.news_date, Users.first_name, Users.second_name) \
        .filter(Users.id == News.id_user).all()
    return render_template("news.html", news=news)


@app.route('/comments_list/<product_id>', methods=("GET", "POST"))
def comments_list(product_id):
    all_comments = comments.get(g.db, product_id)
    return render_template("comments_list.html", comments=all_comments)


@app.route('/contacts')
@breadcrumb('Contacts')
def contacts():
    return render_template("contacts.html")


@app.route('/logout')
@login_required
def logout():
    session.pop("user_id")
    flash("You logged out")
    return redirect(url_for('index'))


@app.route('/login', methods=("GET", "POST"))
@breadcrumb('Login')
def login():
    message = ""
    form = UserLoginForm()
    if request.method == "POST":
        email = form.email.data
        password = form.password.data
        try:
            user = Users.query.filter_by(email=email).first()
            if check_password_hash(user.password, password):
                session['user_id'] = user.id
                flash("You are logged")
                return redirect(url_for('index'))
            else:
                message = "Wrong email or password"
        except AttributeError:
            message = "Wrong email or password"

    return render_template("login.html", form=form, message=message)


@app.route('/registration', methods=("GET", "POST"))
@breadcrumb('Registration')
def registration():
    message = ""
    form = UserRegistrationForm()
    if request.method == "POST":
        first_name = form.first_name.data
        second_name = form.second_name.data
        email = form.email.data
        password = form.password.data
        if validation.register_form_validation(first_name, second_name, password):
            password = generate_password_hash(password)
            try:
                user = Users(first_name=first_name, second_name=second_name, email=email, password=password)
                db.session.add(user)
                db.session.commit()
                flash("Registration was successful")
                return redirect(url_for('index'))
            except IntegrityError:
                message = f"User with email: {email} already exist"
        else:
            message = "Something wrong, check form"

    return render_template("registration.html", message=message, form=form)


@app.route('/admin/add_category', methods=("GET", "POST"))
@login_required
def add_category():
    """Admin: add category"""
    form = AddCategoryForm()
    if request.method == "POST":
        category = ProductCategories(name=form.name.data)
        db.session.add(category)
        db.session.commit()
        flash("Category added")
        return redirect(url_for('categories_list'))
    return render_template("add_category.html", form=form)


@app.route('/admin')
@login_required
def index_admin():
    return render_template("index_admin.html")



@app.route('/admin/add_product', methods=("GET", "POST"))
@login_required
def add_product():
    """function for add product in database"""
    form = AddProductForm()
    form.category_id.choices = [(int(category.id), category.name) for category in ProductCategories.query.all()]
    if request.method == "POST" and form.validate():
        product = Products(name=form.name.data,
                           price=form.price.data,
                           description=form.description.data,
                           category_id=form.category_id.data)
        db.session.add(product)
        db.session.commit()
        save_image_and_thumbnail(form.image.data, product.id)
        flash("Product added")
        return redirect(url_for('products_list'))
    return render_template("add_product.html", form=form)


@app.route('/catalogue/<category>', methods=("GET", "POST"))
@app.route('/catalogue', methods=("GET", "POST"))
@breadcrumb('Catalogue')
def get_catalogue(category="all"):
    categories = ProductCategories.query.all()
    existing_categories = [str(category.id) for category in categories]
    if request.method == "POST":
        if session["user_id"]:
            cart.add(g.db, session["user_id"], request.form.get("add_to_cart", ""))
    if category not in existing_categories and category != "all":
        abort(404)
    products = Products.query.filter_by(deleted=False)
    if category != "all":
        products = products.filter_by(category_id=category, deleted=False)
    return render_template("catalogue.html", categories=categories,
                           products=products.all())


@app.route('/admin/add_news', methods=("GET", "POST"))
@login_required
def add_news():
    form = NewsForm()
    if request.method == 'POST':
        try:
            new_news = News(title=form.title.data, post=form.post.data, id_user=session['user_id'])
            db.session.add(new_news)
            db.session.commit()
            flash('News was successfully added to db.')
        except IntegrityError:
            flash('News wasn\'t added to db.')
        return redirect(url_for('news'))

    return render_template('add_news.html', form=form)


@app.route('/admin/edit_category/<string:category_id>', methods=("GET", "POST"))
@login_required
def edit_category(category_id):
    category = product_categories.read(g.db, category_id)
    if request.method == "POST":
        new_name = request.form.get("new_name", "")
        try:
            product_categories.update(g.db, category_id, new_name)
            flash("Category updated")
            return redirect(url_for('index_admin'))
        except psycopg2.errors.UniqueViolation:
            flash(f"Category {new_name} already exist")
        except errors.StoreError:
            flash("Something wrong, check form")
    return render_template("edit_category.html", category=category)


@app.route("/admin/confirm_delete_category/<category_id>", methods=("GET", "POST"))
@login_required
def confirm_delete_category(category_id):
    category_ = product_categories.read(g.db, category_id)
    return render_template("confirm_delete_category.html", id=category_id, category=category_)


@app.route("/admin/confirm_delete_category/delete/<category_id>", methods=("GET", "POST"))
@login_required
def delete_category(category_id):
    product_categories.delete(g.db, category_id)
    flash("Deleted")
    return redirect(url_for('categories_list'))


@app.route('/admin/products_list', methods=("GET", "POST"))
@login_required
def products_list():
    products = db.session.query(Products).order_by(Products.id).all()
    categories = {}
    for product in products:
        categories[product.category_id] = db.session.query(ProductCategories).filter_by(id=product.category_id).first().name
    return render_template("products_list.html", products=products, categories=categories)


@app.route('/admin/edit_product/<string:product_id>', methods=("GET", "POST"))
@login_required
def edit_product(product_id):
    product = products.get_product_2(g.db, product_id)
    categories = product_categories.get_all(g.db)
    if request.method == "POST":
        id = request.form.get("product_id", "")
        name = request.form.get("product_name", "")
        price = request.form.get("price", "")
        img = request.files['img'].read()
        category = request.form.get("category", "")
        try:
            products.edit_product_2(g.db, id, name, price, category, img)
            flash("Product edited")
            return redirect(url_for('products_list'))
        except errors.StoreError:
            flash("Smth wrong, pls try again")
    return render_template("edit_product.html", product=product, categories=categories)


@app.route('/admin/delete_news', methods=("GET", "POST"))
@login_required
def delete_news():
    news = db.session.query(News) \
        .join(Users) \
        .add_columns(News.id, News.title, News.post, News.news_date,
                     Users.first_name, Users.second_name) \
        .filter(Users.id == News.id_user).all()
    return render_template("delete_news.html", news=news)


@app.route('/admin/delete_news/<string:news_id>', methods=("GET", "POST"))
@login_required
def delete_news_id(news_id):
    News.query.filter(News.id == news_id).delete()
    db.session.commit()
    flash('News was successfully deleted from db.')
    return redirect(url_for('delete_news'))


@app.route('/admin/edit_news', methods=("GET", "POST"))
@login_required
def edit_news():
    news = db.session.query(News) \
        .join(Users) \
        .add_columns(News.id, News.title, News.post, News.news_date,
                     Users.first_name, Users.second_name) \
        .filter(Users.id == News.id_user).all()
    return render_template("edit_news.html", news=news)


@app.route('/admin/edit_news/<string:news_id>', methods=("GET", "POST"))
@login_required
def edit_news_id(news_id):
    post = News.query.filter(News.id == news_id).first()
    if request.method == 'POST':
        form = NewsForm(formdata=request.form, obj=post)
        form.populate_obj(post)
        db.session.commit()
        flash('News was successfully updated in db.')
        return redirect(url_for('edit_news'))
    form = NewsForm(obj=post)
    return render_template('edit_news_id.html', post=post, form=form)


@app.route("/admin/delete_product", methods=("GET", "POST"))
@login_required
def delete_product():
    all_products = products.get_all(g.db)
    return render_template("delete_product.html", products=all_products)


@app.route("/admin/delete_confirm/<product_id>", methods=("GET", "POST"))
@login_required
def delete_confirm(product_id):
    product = db.session.query(Products).filter_by(id = product_id).first()
    return render_template("delete_confirm.html", product=product)


@app.route("/admin/delete_confirm/delete/<product_id>", methods=("GET", "POST"))
@login_required
def delete(product_id):
    Products.query.filter_by(id=product_id).delete()
    db.session.commit()
    return redirect(url_for('products_list'))


@app.route('/admin/categories_list', methods=("GET", "POST"))
@login_required
def categories_list():
    page = request.args.get('page', 1, type=int)
    categories = ProductCategories.query.paginate(page, 3, False)
    next_url = url_for('categories_list', page=categories.next_num) \
        if categories.has_next else None
    prev_url = url_for('categories_list', page=categories.prev_num) \
        if categories.has_prev else None
    print(categories.items)
    # print(categories.items[0])

    return render_template("categories_list.html", categories=categories.items,
                           next_url=next_url, prev_url=prev_url)


@app.context_processor
def inject_email():
    user_email = ''
    if 'user_id' in session:
        user = Users.query.filter_by(id=session['user_id']).first()
        user_email = user.email
    return {'user_email': user_email}
