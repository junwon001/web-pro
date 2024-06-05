from flask import Flask, render_template, url_for, redirect, request, session, flash, jsonify, g
from pymongo import MongoClient
from bson.objectid import ObjectId
import functools
import bcrypt
import os
from os.path import join, dirname, realpath
from werkzeug.utils import secure_filename
from datetime import datetime
from bs4 import BeautifulSoup  # BeautifulSoup 추가

client = MongoClient("mongodb://localhost:27017/")
db = client["webapp"]
projects_col = db.projects
posts_col = db.posts
contacts_col = db.contacts
settings_col = db.settings
user_col = db['user']
travel_col = db['travel']

app = Flask(__name__)

PATH_UPLOAD = 'static/uploads'
FULL_UPLOAD_FOLDER = join(dirname(realpath(__file__)), PATH_UPLOAD)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = FULL_UPLOAD_FOLDER
app.secret_key = 'fad62b7c1a6a9e67dbb66c3571a23ff2425650965f80047ea2fadce543b088cf'

def update_setting_data(_id, updatedvalues):
    _id_converted = ObjectId(_id)
    query_by_id = {"_id": _id_converted}
    new_updated_value = { "$set": updatedvalues }
    settings_col.update_one(query_by_id, new_updated_value)

def upload_image_file(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        generated_datetime = datetime.now().strftime('%Y%m%d%H%M%S%f')
        filename = generated_datetime+"_"+filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    else:
        flash('Allowed image types are -> png, jpg, jpeg, gif')
        return ""

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        user_email = session.get('user_email')
        if user_email is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def skiplimit(col, page_size, page_num):
    skips = page_size * (page_num - 1)
    cursor = col.find().sort("_id", -1).skip(skips).limit(page_size)
    return list(cursor)

@app.before_request
def before_request():
    g.current_time = datetime.now()

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'uploadfile' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['uploadfile']
        if file.filename == '':
            flash('No image selected for uploading')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('Image successfully uploaded and displayed below')
            return render_template('uploadform.html', filename=filename)
        else:
            flash('Allowed image types are -> png, jpg, jpeg, gif')
            return redirect(request.url)
        
    return render_template('uploadform.html')

@app.route('/display/<filename>')
def display_image(filename):
    return redirect(url_for('static', filename='uploads/' + filename), code=301)

def refreshSettingSessionData():
    setting_data = settings_col.find_one()
    session["website_name"] = setting_data["website_name"]
    session["tagline"] = setting_data["tagline"]
    session["profile_img"] = setting_data["profile_img"]

@app.route('/')
def index():
    website_name = session.get('website_name')
    if (website_name is None):
        refreshSettingSessionData()

    post_data = posts_col.find({}).sort("_id", -1).limit(3)
    post_data_list = list(post_data)
    project_data = projects_col.find({}).sort("_id", -1).limit(2)
    project_data_list = list(project_data)
    
    return render_template("home.html", posts=post_data_list, projects=project_data_list)

@app.route('/about')
def about():
    about_data = settings_col.find_one()
    return render_template("about.html", data=about_data)

@app.route('/projects')
def projects():
    project_data = projects_col.find({}).sort("_id", -1)
    project_data_list = list(project_data)
    return render_template("projects.html", data=project_data_list)

@app.route('/projects/detail/<id>')
def projects_detail(id):
    project_data = ""
    try:
        _id_converted = ObjectId(id)
        search_filter = {"_id": _id_converted}
        project_data = projects_col.find_one(search_filter)
    except:
        print("ID is not found/invalid")
    
    return render_template("projects_detail.html", data=project_data)

@app.route('/posts')
def posts():
    page_size = 10
    page_num = request.args.get('page')
    if page_num is None:
        page_num = 1
    else:
        page_num = int(page_num)

    data = skiplimit(posts_col, page_size, page_num)
    
    last_data = False
    if len(data) == 0:
        last_data = True

    for post in data:
        if 'views' not in post:
            post['views'] = 0
        if 'likes' not in post:
            post['likes'] = 0

    return render_template("posts.html", data=data, page=page_num, last_data=last_data)

@app.route('/posts/detail/<id>')
@login_required
def posts_detail(id):
    post_data = ""
    try:
        _id_converted = ObjectId(id)
        search_filter = {"_id": _id_converted}
        post_data = posts_col.find_one(search_filter)
        if post_data:
            posts_col.update_one(search_filter, {"$inc": {"views": 1}})
    except:
        print("ID is not found/invalid")

    return render_template("posts_detail.html", data=post_data)

@app.route('/new_post', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title'].strip()
        tags = request.form['tags'].strip()
        content = request.form['content'].strip()
        author = session['user_email']

        # HTML 태그 제거
        soup = BeautifulSoup(content, "html.parser")
        content_text_only = soup.get_text()
        
        image_filename = ''
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                image_filename = upload_image_file(file)
        
        new_post_data = {
            "title": title,
            "tags": tags,
            "content": content_text_only,  # HTML 태그가 제거된 콘텐츠
            "author": author,
            "created_date": datetime.now(),
            "views": 0,
            "likes": 0,
            "image": image_filename
        }
        posts_col.insert_one(new_post_data)
        flash("Post created successfully.")
        return redirect(url_for('posts'))

    return render_template('new_post.html')

@app.route('/posts/comment/new/<id>', methods=['POST'])
def new_comment(id):
    _id = request.form['_id'].strip()
    email = request.form['email'].strip()
    name = request.form['name'].strip()
    content = request.form['content'].strip()

    new_comment = { "email": email, "name": name, "content": content, "created_date": datetime.now() }

    _id_converted = ObjectId(_id)
    search_filter = {"_id": _id_converted}
    post_data = posts_col.find_one(search_filter)
    
    comments = list()
    
    if post_data.__contains__("comments"):
        comments = list(post_data['comments'])

    comments.append(new_comment.copy())

    query_by_id = {"_id": _id_converted}
    new_updated_comments = { "$set": { "comments": comments } }
    posts_col.update_one(query_by_id, new_updated_comments)

    flash("Your comment has been successfully received.")
    return redirect(url_for('posts_detail', id=id))

@app.route('/posts/recommend/<id>', methods=['POST'])
@login_required
def recommend_post(id):
    user_email = session['user_email']
    try:
        _id_converted = ObjectId(id)
        search_filter = {"_id": _id_converted}
        post_data = posts_col.find_one(search_filter)
        
        if post_data:
            if 'recommendations' not in post_data:
                post_data['recommendations'] = []
            
            if user_email not in post_data['recommendations']:
                new_likes = post_data.get('likes', 0) + 1
                post_data['recommendations'].append(user_email)
                
                posts_col.update_one(search_filter, {
                    "$set": {
                        "likes": new_likes,
                        "recommendations": post_data['recommendations']
                    }
                })
                flash("Thank you for recommending this post!")
            else:
                flash("You have already recommended this post.", "info")
        else:
            flash("Post not found.", "error")
    except:
        flash("An error occurred. Please try again.", "error")

    return redirect(url_for('posts_detail', id=id))


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == "POST":
        email = request.form['email'].strip()
        subject = request.form['subject'].strip()
        name = request.form['name'].strip()
        content = request.form['content'].strip()

        new_contact_data = { "email": email, "subject": subject, "name": name, "content": content, "created_date": datetime.now() }
        contacts_col.insert_one(new_contact_data)
        return render_template("thankyou.html")

    return render_template("contact.html")

@app.route('/admin/projects')
@login_required
def admin_projects():
    project_data = projects_col.find({}).sort("_id", -1)
    project_data_list = list(project_data)
    return render_template("admin/projects.html", data=project_data_list)

@app.route('/admin/projects/new', methods=['GET', 'POST'])
@login_required
def admin_new_project():
    if request.method == 'POST':
        file = request.files['image']
        title = request.form['title'].strip()
        funder = request.form['funder'].strip()
        duration = request.form['duration'].strip()
        content = request.form['content'].strip()
        
        new_data = { "title": title, "funder": funder, "duration": duration, "content": content, "created_date": datetime.now()}
        
        if file.filename != '':
            image_filename = upload_image_file(file)
            if image_filename:
                new_data["image"] = image_filename
        projects_col.insert_one(new_data)
        flash("The data has been successfully saved.")
        return redirect(url_for('admin_projects'))

    return render_template("admin/new_project.html")

@app.route('/admin/projects/update/<id>', methods=['GET', 'POST'])
@login_required
def admin_update_project(id):
    if request.method == 'POST':
        file = request.files['image']
        _id = request.form['_id'].strip()
        title = request.form['title'].strip()
        funder = request.form['funder'].strip()
        duration = request.form['duration'].strip()
        content = request.form['content'].strip()

        updatedvalues = { "title": title, "funder": funder, "duration": duration, "content": content }
        
        if file.filename != '':
            image_filename = upload_image_file(file)
            if image_filename:
                updatedvalues["image"] = image_filename
        update_project_data(_id, updatedvalues)
        flash("The data has been successfully updated.")
        return redirect(url_for('admin_projects'))

    data = ""
    try:
        _id_converted = ObjectId(id)
        search_filter = {"_id": _id_converted}
        data = projects_col.find_one(search_filter)
    except:
        print("ID is not found/invalid")

    return render_template("admin/update_project.html", data=data)

def update_project_data(_id, updatedvalues):
    _id_converted = ObjectId(_id)
    query_by_id = {"_id": _id_converted}
    new_updated_value = { "$set": updatedvalues }
    projects_col.update_one(query_by_id, new_updated_value)

@app.route('/admin/projects/delete/<id>', methods=['POST'])
@login_required
def admin_delete_project(id):
    if request.method == "POST":
        _id_converted = ObjectId(id)
        query_by_id = {"_id": _id_converted}
        projects_col.delete_one(query_by_id)
        flash("The data has been successfully deleted.")
        return redirect(url_for('admin_projects'))

@app.route('/admin/posts')
@login_required
def admin_posts():
    posts_data = posts_col.find({}).sort("_id", -1)
    posts_data_list = list(posts_data)
    return render_template("admin/posts.html", data=posts_data_list)

@app.route('/admin/posts/new', methods=['GET', 'POST'])
@login_required
def admin_new_post():
    if request.method == 'POST':
        file = request.files['image']
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        content = request.form['content'].strip()
        
        new_data = { "title": title, "author": author, "content": content, "created_date": datetime.now()}
        
        if file.filename != '':
            image_filename = upload_image_file(file)
            if image_filename:
                new_data["image"] = image_filename
        posts_col.insert_one(new_data)
        flash("The data has been successfully saved.")
        return redirect(url_for('admin_posts'))

    return render_template("admin/new_post.html")

@app.route('/admin/posts/update/<id>', methods=['GET', 'POST'])
@login_required
def admin_update_post(id):
    if request.method == 'POST':
        file = request.files['image']
        _id = request.form['_id'].strip()
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        content = request.form['content'].strip()

        updatedvalues = { "title": title, "author": author, "content": content}
        
        if file.filename != '':
            image_filename = upload_image_file(file)
            if image_filename:
                updatedvalues["image"] = image_filename
        update_post_data(id, updatedvalues)
        flash("The data has been successfully updated.")
        return redirect(url_for('admin_posts'))

    data = ""
    try:
        _id_converted = ObjectId(id)
        search_filter = {"_id": _id_converted}
        data = posts_col.find_one(search_filter)
    except:
        print("ID is not found/invalid")

    return render_template("admin/update_post.html", data=data)

def update_post_data(_id, updatedvalues):
    _id_converted = ObjectId(_id)
    query_by_id = {"_id": _id_converted}
    new_updated_value = { "$set": updatedvalues }
    posts_col.update_one(query_by_id, new_updated_value)

@app.route('/admin/posts/delete/<id>', methods=['POST'])
@login_required
def admin_delete_post(id):
    if request.method == "POST":
        _id_converted = ObjectId(id)
        query_by_id = {"_id": _id_converted}
        posts_col.delete_one(query_by_id)
        flash("The data has been successfully deleted.")
        return redirect(url_for('admin_posts'))

@app.route('/admin/contacts')
@login_required
def admin_contacts():
    contact_data = contacts_col.find({}).sort("_id", -1)
    contact_data_list = list(contact_data)
    return render_template("admin/contacts.html", data=contact_data_list)

@app.route('/admin/contacts/read/<id>')
@login_required
def admin_read_contact(id):
    data = ""
    try:
        _id_converted = ObjectId(id)
        search_filter = {"_id": _id_converted}
        data = contacts_col.find_one(search_filter)
    except:
        print("ID is not found/invalid")

    return render_template("admin/read_contact.html", data=data)

@app.route('/admin/contacts/delete/<id>', methods=['POST'])
@login_required
def admin_delete_contact(id):
    if request.method == "POST":
        _id_converted = ObjectId(id)
        query_by_id = {"_id": _id_converted}
        contacts_col.delete_one(query_by_id)
        flash("The data has been successfully deleted.")
        return redirect(url_for('admin_contacts'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    if request.method == 'POST':
        file = request.files['profile_img']
        _id = request.form['_id'].strip()
        website_name = request.form['website_name'].strip()
        tagline = request.form['tagline'].strip()
        about = request.form['about'].strip()

        updatedvalues = { "website_name": website_name, "tagline": tagline, "about": about }
        
        if file.filename != '':
            image_filename = upload_image_file(file)
            if image_filename:
                updatedvalues["profile_img"] = image_filename
        update_setting_data(_id, updatedvalues)
        refreshSettingSessionData()
        flash("The data has been successfully updated.")
        return redirect(url_for('admin_settings'))

    setting_data = settings_col.find_one()
    return render_template("admin/settings.html", data=setting_data)

@app.route('/sign', methods=['GET', 'POST'])
def sign_in():
    if request.method == "POST":
        _id = request.form['Id/Email'].strip()
        password = request.form['password'].strip()
        password2 = request.form['password2'].strip()
        if password == password2:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            new_user_info = {"email": _id, "password": hashed_password.decode('utf-8')}
            user_col.insert_one(new_user_info)
            return redirect(url_for('login'))
        else:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return redirect(url_for('sign_in'))
    return render_template("sign.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        
        user_data = user_col.find_one({"email": email})
        
        if user_data:
            user_data_password = user_data['password']
            
            if bcrypt.checkpw(password.encode('utf-8'), user_data_password.encode('utf-8')):
                session["user_email"] = email
                return redirect(url_for('admin_projects'))
            else:
                flash('Email/password is invalid. Please try again.')
                return redirect(url_for('login'))
        
        flash('로그인에 실패했습니다. 비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('login'))
    
    user_email = session.get('user_email')
    if user_email:
        return redirect(url_for('admin_projects'))
    
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/get_subregions', methods=['POST'])
def get_subregions():
    region1 = request.json.get('region1')
    subregions = {
        '경기도': ['수원시', '성남시', '의정부시', '안양시'],
        '강원도': ['춘천시', '원주시', '강릉시']
    }
    return jsonify(subregions.get(region1, []))

@app.route('/get_travels', methods=['POST'])
def get_travels():
    region1 = request.json.get('region1')
    region2 = request.json.get('region2')
    
    travels = travel_col.find({'region1': region1, 'region2': region2}, {'_id': 0, 'travel': 1})
    travel_list = [travel['travel'] for travel in travels]
    
    return jsonify(travel_list)

@app.route('/get_travel_info', methods=['POST'])
def get_travel_info():
    travel_name = request.json.get('travel_name')
    
    travel_info = travel_col.find_one({'travel': travel_name}, {'_id': 0, 'travel': 1, 'about': 1, 'profile_img': 1})
    
    return jsonify(travel_info)

if __name__ == '__main__':
    app.run(debug=True)
