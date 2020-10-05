#NOTE: to run this script, just enter the directory where this python file is and type python simo-app.py
from flask import Flask,redirect,url_for,render_template, request, session, flash
#note: pip install flask is required in the local environment
#redirect, allows redirection from certain urls
#url_for, allows to choose where to redirect
#render_template allows to render html templates in the folder template
#request allows to use and manipulate results from http requests (GET, POST)
#session allows to manage sessions, during which data sent to the server are stored locally - NB: every time we close the web page, all the data of the session are erased
#flash allows the usage of flash messaging
from datetime import timedelta
#allows setting the time for permanent session duration
from libraries.contentful import Contentful
#note: pip install contentful is required in the local environment
#Contentful allows easy article management without a database 
from rich_text_renderer import RichTextRenderer
#requires pip install rich_text_renderer
#allows better rendering of articles
import os
#os allows to manipulate information within the local os
from dotenv import load_dotenv
#requires pip install python-dotenv
load_dotenv()
#loading information in .env file (e.g. secret keys)
from flask_sqlalchemy import SQLAlchemy
#requires pip install flask-sqlalchemy
#allows use of databases




#launching the Flask app
app = Flask(__name__)
#setting up a secret key to encript all the data shared with the server through POST calls
app.secret_key= "hello"
#setting validity time of permanent sessions (how long data are stored in server, even though we close web page)
app.permanent_session_lifetime= timedelta(minutes=5)

#defining keys and values of NavBar (they will be name and href)
navbar = {
    'home': '/',
    'login': '/login',
    'logout': '/logout',
    'user': '/user'
}


#HOME PAGE
#decorator with route to home page and html string
@app.route("/")
def home():

# version1 with in-line html
# return "Hello, this is the main page of the Website <h1> Main Page <h1>"

#getting all articles from Contentful space
 articles = Contentful.get_all_articles()


#version 2: rendering of home_page html file with information passed about navbar and contentful articles
 return render_template("index_inher.html",
  navbar=navbar,
  articles=articles
  )

#LOGIN PAGE 
#Testing GET(non secure, visible to all) and POST (more secure) methods for http calls
@app.route("/login", methods= ["POST", "GET"])
def login(): 
#if user arrives through post call, so presses submit button, is redirected to user page with the name typed in submit form 
  if request.method == "POST":
    session.permanent=True #after login, the session becomes permanent for as long as we want it to
    user=request.form["nm"] #note: request.form is a dictionary, so we can access via keys
    session["user"]=user #creating a session name after the user that has filled in the login form
    flash(f"You have successfully logged in, {user}", "info") 
    return redirect(url_for("user")) #after login, user is redirected to user page
#if user arrives through get call, so from other page, sees login form
  else:
    if "user" in session:
          user=session["user"]
          flash(f"You are already logged in, {user}", "info")
          return redirect(url_for("user")) 
    
    return render_template("login_page.html",
  navbar=navbar)

@app.route("/logout")
def logout():
   #checks if a specific user has already logged in, only in that case the logout message appears
   if "user" in session: 
      user=session["user"]
      #includes flash message content and cathegory
      flash(f"You have successfully logged out, {user}", "info") 
   else:
      flash(f"You need to login first", "info")  
   #erases user session data during logout
   session.pop("user", None)    
   session.pop("email", None) 
   return redirect(url_for("login"))

@app.route("/user", methods= ["POST", "GET"])
def user():
    email = None
    if "user" in session: #checks if a specific user has already logged in
      user=session["user"]
      #if the request method is POST (form submission), get the email from the form
      if request.method == "POST":
       email=request.form["email"]
       session["email"]=email
      #if the request method is GET (so it is a refresh, or generally not a form submission), get the email address from the session
      else:
        if "email" in session:
          email=session["email"]

      return render_template("user_page.html",
       user=user,
       navbar=navbar,
       email=email)
    else: 
        flash(f"You need to login first", "info")
        return redirect(url_for("login")) #if not already logged, user must log

#ANOTHER PAGE (WELCOME)
#page getting the url last argument as input
#version 1: simple in line html
#@app.route("/user")
#def user(name="user"):
#    return render_template("user_name.html",content=name)
#version 2: rendering html template inserting content from url
#@app.route("/<name>")
#def user(name):
# return f"Welcome to this page {name}"

#BLOG
@app.route('/blog/<slug>')
def article(slug):
    article = Contentful.get_article_by_slug(slug)
    renderer = RichTextRenderer()
    article.html = renderer.render(article.content)
    return render_template('article.html',
        navbar=navbar,
        article=article
    )
    


#ADMIN PAGE WITH REDIRECT
#redirecting to home for some routes (needs installation of redirect and url_for packages)
@app.route("/admin")
def admin(): 
     return redirect(url_for('home'))

#redirecting to a specific function requiring an input 
@app.route("/theadmin")
def theadmin():
    return redirect(url_for("user", name="YouAreTheAdmin!"))

if __name__=="__main__":
#adding debug=True allows debugging online and prevents us from re-running the simo-app.py every time
 app.run(debug=True)

