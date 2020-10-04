#NOTE: to run this script, just enter the directory where this python file is and type python simo-app.py
from flask import Flask,redirect,url_for,render_template, request, session
#note: pip install flask is required in the local environment
#redirect, allows redirection from certain urls
#url_for, allows to choose where to redirect
#render_template allows to render html templates in the folder template
#request allows to use and manipulate results from http requests (GET, POST)
#session allows to manage sessions, during which data sent to the server are stored locally - NB: every time we close the web page, all the data of the session are erased
from libraries.contentful import Contentful
#note: pip install contentful is required in the local environment
#Contentful allows easy article management without a database 
import os
#os allows to manipulate information within the local os
from dotenv import load_dotenv
#requires pip install python-dotenv
#loading information in .env file (e.g. secret keys)
load_dotenv()




#launching the Flask app
app = Flask(__name__)
#setting up a secret key to encript all the data shared with the server through POST calls
app.secret_key= "hello"

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
    user=request.form["nm"] #note: request.form is a dictionary, so we can access via keys
    session["user"]=user #creating a session name after the user that has filled in the login form
    return redirect(url_for("user")) #after login, user is redirected to user page
#if user arrives through get call, so from other page, sees login form
  else:
    if "user" in session:
          return redirect(url_for("user")) 
    
    return render_template("login_page.html",
  navbar=navbar)

@app.route("/logout")
def logout():
   session.pop("user", None) #erases user session
   return redirect(url_for("login"))

@app.route("/user")
def user():
    if "user" in session: #checks if a specific user has already logged in
      user=session["user"]
      return render_template("user_page.html",
       user=user,
       navbar=navbar)
    else: 
        return redirect(url_for("login")) #if not already logged, user must log


#TEST PAGE
@app.route("/test")
def test(): 
    return render_template("new.html")


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

