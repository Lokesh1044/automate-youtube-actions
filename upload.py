import json
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate('static/db/automate--actions-firebase-adminsdk-6a4w9-3109e33267.json')
firebase_admin.initialize_app(cred)

# Create Firestore client
db = firestore.client()

def upload_json_to_db(json_file_path):
    try:
        # Read the JSON file
        with open(json_file_path, 'r') as file:
            data = json.load(file)

        # Check if 'comments' key exists in the data
        if 'comments' in data:
            comments = data['comments']
            # Upload all comments to the specified document in Firestore
            db.collection('comments').document('Entertainment').set({'comments': comments})

            print("Data uploaded to Firestore successfully.")
        else:
            print("No 'comments' key found in the JSON data.")

    except Exception as e:
        print(f"Error uploading data to Firestore: {e}")

# Call the function with the path to your JSON file
upload_json_to_db('static/jsons/Entertainment.json')
