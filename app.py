from flask import Flask, render_template, request, redirect, url_for
import json
import time
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import firebase_admin
from firebase_admin import credentials, firestore
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import praw
from bs4 import BeautifulSoup
import openai
import re


app = Flask(__name__)

# Initialize Firebase Admin SDK
cred = credentials.Certificate('static\\db\\automate--actions-firebase-adminsdk-6a4w9-3109e33267.json')
firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

openai.api_key = 'Authorization: Bearer OPENAI_API_KEY'

available_accounts = []
global_comments_array = []

# Save cookies to Firestore
def save_cookies_to_db(cookies, account_name):
    try:
        db.collection('accounts').document(account_name).set({
            'account_name': account_name,
            'cookies': json.dumps(cookies),
            'status': 'available'
        })
        print("Cookies saved to Firestore.")
    except Exception as e:
        print(f"Error saving cookies to Firestore: {e}")

def account_exists(account_name):
    account_ref = db.collection('accounts').document(account_name).get()
    return account_ref.exists

def create_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--headless")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get("https://www.youtube.com")
    
    return driver

# Load available accounts from Firestore
def load_available_accounts():
    global available_accounts
    try:
        accounts_ref = db.collection('accounts').where('status', '==', 'available').stream()
        available_accounts = [(doc.id, doc.to_dict()['cookies']) for doc in accounts_ref]
    except Exception as e:
        print(f"Error loading accounts from Firestore: {e}")
        available_accounts = []

# Load available accounts in a background thread
def load_accounts_background():
    while True:
        load_available_accounts()
        time.sleep(60)  

# Mark account as "in_use"
def mark_account_in_use(account_name):
    try:
        db.collection('accounts').document(account_name).update({'status': 'in_use'})
        print(f"Account {account_name} marked as 'in_use'.")
    except Exception as e:
        print(f"Error marking account as 'in_use' in Firestore: {e}")

# Mark account as "available"
def mark_account_available(account_name):
    try:
        db.collection('accounts').document(account_name).update({'status': 'available'})
        print(f"Account {account_name} marked as 'available'.")
    except Exception as e:
        print(f"Error marking account as 'available' in Firestore: {e}")

# Perform YouTube actions
def perform_youtube_actions(driver, video_url, account_name):
    try:
        driver.get(video_url)
        print(f"Video page loaded successfully for {account_name}: {driver.title}")

        # Fetch the video title
        video_title = driver.title
        print(f"Fetched video title: {video_title}") 

        # Like the video
        like_video(driver, account_name)

        # Subscribe the channel
        page_source = driver.page_source
        match = re.search(r'"subscribed":(true|false)', page_source)
        print(match)
        try:
            if match:
                subscribed_status = match.group(1) == 'true'  
                print("Subscribed Status:", subscribed_status)

                if not subscribed_status:
                    subscribe_to_channel(driver, account_name)
                else:
                    print(f"Already subscribed to the channel for {account_name}. No action taken.")
            else:
                print("Subscribed status not found.")

        except Exception as e:
            print(f"An error occurred: {e}")

        # Post comment on video
        try:
            subscribed_status = match.group(1) == 'true' 
            if not subscribed_status:
                print("User is not subscribed, proceeding normally.")
                post_comment(driver, account_name)                
            else:
                print("User is subscribed, handling subscription-specific logic.")
                subscribed_user_post_comment(driver, account_name)                
        except Exception as e:
            print(f"An error occurred: {e}")        

        driver.quit()
    except Exception as e:
        driver.quit()
        print(f"Error during YouTube interaction for {account_name}: {e}")


# Like the video
def like_video(driver, account_name):
    try:
        like_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'like this')]"))
        )
        aria_pressed = like_button.get_attribute("aria-pressed")        
        if aria_pressed == "true":
            print(f"Video already liked for {account_name}. No action taken.")
        else:
            driver.execute_script("arguments[0].scrollIntoView(true);", like_button)
            driver.execute_script("arguments[0].click();", like_button)
            print(f"Video liked for {account_name}.")
    except Exception as e:
        print(f"Failed to like the video for {account_name}: {e}")

# Subscribe to channel
def subscribe_to_channel(driver, account_name):   
    try:
        subscribe_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Subscribe')]"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", subscribe_button)
        driver.execute_script("arguments[0].click();", subscribe_button)
        print(f"Subscribed to the channel for {account_name}.")
    except Exception as e:
        print(f"Failed to subscribe to the channel for {account_name}: {e}")
    
#post comment for subscribed users
def subscribed_user_post_comment(driver, account_name):
    if not global_comments_array:
        print("No comments available to post.")
        return
    
    comment = random.choice(global_comments_array)
    print("Selected comment:", comment)
    global_comments_array.remove(comment)

    try:
        print("Waiting for the comment box...")
        comment_box = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.XPATH, "//*[@id='simplebox-placeholder']"))
        )
        print("Comment box found:", comment_box)

        driver.execute_script("arguments[0].scrollIntoView(true);", comment_box)
        comment_box.click()  # Directly click the comment box

        # Wait for the input box to become visible
        input_box = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='contenteditable-root']"))
        )
        print("Focusing on input box...")
        driver.execute_script("arguments[0].focus();", input_box)

        print("Entering comment...")
        driver.execute_script("arguments[0].innerHTML = arguments[1];", input_box, comment['text'])

        post_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@id='submit-button']"))
        )
        print("Clicking on post button...")
        post_button.click()  # Use direct click here
        print("Comment posted successfully.")

    except Exception as e:
        print(f"Failed to post the comment: {e}")


# Post a comment
def post_comment(driver, account_name):
    if not global_comments_array:
        print("No comments available to post.")
        return
    comment = random.choice(global_comments_array)
    print("comment------->",comment)
    global_comments_array.remove(comment)

    try:
        print("Before Clicking on comment box...")
        comment_box = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.XPATH, "//*[@id='simplebox-placeholder']"))
        )
        print("...> ",comment_box)
        driver.execute_script("arguments[0].scrollIntoView(true);", comment_box)
        print("Clicking on comment box...")
        driver.execute_script("arguments[0].click();", comment_box)
        input_box = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='contenteditable-root']"))
        )
        print("Entering comment...")
        driver.execute_script("arguments[0].focus();", input_box)
        driver.execute_script("arguments[0].innerText = arguments[1];", input_box, comment['text'])
        post_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@id='submit-button']"))
        )
        print("Clicking on post button...")
        driver.execute_script("arguments[0].click();", post_button)
        print("Comment posted successfully.")
    except Exception as e:
        print(f"Failed to post the comment: {e}")

# Process YouTube actions in a thread
def process_account(account_name, cookies, video_url):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get("https://www.youtube.com")
    time.sleep(3)

    for cookie in json.loads(cookies):
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            print(f"Error adding cookie for {account_name}: {e}")

    mark_account_in_use(account_name)
    driver.refresh()

    perform_youtube_actions(driver, video_url, account_name)
    mark_account_available(account_name)

def get_comments_from_category(video_url,driver):
    driver.get(video_url)
    category_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'meta[itemprop="genre"]'))
        )
    video_category = category_element.get_attribute('content')
    print(f"Video category: {video_category}")
    try:
        global global_comments_array
        doc_ref = db.collection('comments').document(video_category)
        print(doc_ref)
        doc = doc_ref.get()

        if doc.exists:
            comments_data = doc.to_dict()
            global_comments_array = comments_data.get('comments', [])
    
    except Exception as e:
        print(f"Error fetching comments from Firebase: {e}")
        return []

def message(msg):
    return render_template('index.html', message=msg)

# Flask Routes
@app.route('/')
def home():
    load_available_accounts()
    return render_template('index.html')

@app.route('/get_available_accounts', methods=['GET'])
def get_available_accounts():
    accounts = available_accounts  
    return {"count": len(accounts)}

@app.route('/submit', methods=['POST'])
def submit():    
    account_choice = request.form['account_choice']

    if account_choice == 'new':
        account_name = request.form['account_name']

        if account_exists(account_name):
            return message(msg=f"Account name '{account_name}' already exists! Please choose another account name.")

        # Launch the browser to allow the user to log in manually
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.get("https://www.youtube.com")
        print("Please log in to YouTube manually...")
        try:
            WebDriverWait(driver, 300).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button#avatar-btn")) 
            )
            print("Login successful.")
        except Exception as e:
            print("Login failed or timeout:", e)
        
        # After login, get the cookies and save them
        cookies = driver.get_cookies()
        save_cookies_to_db(cookies, account_name)
        print("Cookies:", cookies)
        return message(msg=f"Account {account_name} successfully added to DB.")

    elif account_choice == 'old':
        accounts = available_accounts
        video_url = request.form['video_url']
        num_accounts = int(request.form['num_accounts'])

        if not accounts:
            return message(msg=f"No available accounts found.")
        elif num_accounts <= len(accounts):
            selected_accounts = random.sample(accounts, num_accounts)
        else:
            selected_accounts = accounts

        if not video_url:
            return message(msg=f"Please Enter video URL!")
        
        driver = create_driver()
        get_comments_from_category(video_url,driver) 
        print("global_comments_array------>",global_comments_array)   

        # Create threads to process accounts
        threads = []
        for account in selected_accounts:
            account_name, cookies = account
            thread = threading.Thread(target=process_account, args=(account_name, cookies, video_url))
            threads.append(thread)
            thread.start()
            time.sleep(1)  

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

    return message(msg=f"Automated Actions completed for random Accounts.")

if __name__ == '__main__':
    threading.Thread(target=load_accounts_background, daemon=True).start()
    app.run(debug=True)
