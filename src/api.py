import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
import uvicorn
from pydantic import BaseModel
import datetime
from pathlib import Path

# Pydantic models for request and response bodies
class Question(BaseModel):
    question_id: str
    question_text: str

class Answer(BaseModel):
    answer_text: str

class QuestionUpdate(BaseModel):
    answer_text: str | None = None
    status: str | None = None

# Initialize FastAPI app
app = FastAPI()

# Initialize Jinja2Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# Initialize Firebase Admin SDK

# Build a robust path to the credentials file

script_dir = Path(__file__).parent

CREDENTIALS_FILE = script_dir.parent / "salon-queries-firebase-adminsdk-fbsvc-04787d1c4d.json"



try:

    cred = credentials.Certificate(CREDENTIALS_FILE)

    firebase_admin.initialize_app(cred)

    db = firestore.client()

except Exception as e:

    print(f"Error initializing Firebase: {e}")

    db = None

@app.post("/questions")
def create_question(question: Question):
    if not db:
        return {"error": "Database not initialized"}
    doc_ref = db.collection('questions').document(question.question_id)
    doc_ref.set({
        'question_text': question.question_text,
        'status': 'pending',
        'timestamp': datetime.datetime.now(tz=datetime.timezone.utc)
    })
    return {"question_id": question.question_id, "status": "pending"}

@app.get("/questions")
def get_questions(status: str = 'pending'):
    if not db:
        return {"error": "Database not initialized"}
    
    if status == 'all':
        questions_ref = db.collection('questions').stream()
    else:
        questions_ref = db.collection('questions').where('status', '==', status).stream()
        
    questions = []
    for q in questions_ref:
        question_data = q.to_dict()
        question_data["id"] = q.id
        questions.append(question_data)
    return {"questions": questions}

@app.get("/questions/{question_id}")
def get_question(question_id: str):
    if not db:
        return {"error": "Database not initialized"}
    doc_ref = db.collection('questions').document(question_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        return {"error": "Question not found"}

@app.put("/questions/{question_id}")
def update_question(question_id: str, update: QuestionUpdate):
    if not db:
        return {"error": "Database not initialized"}
    
    update_data = {}
    if update.answer_text is not None:
        update_data['answer_text'] = update.answer_text
        update_data['status'] = 'answered' # Automatically set to answered if an answer is provided
    if update.status is not None:
        update_data['status'] = update.status

    if not update_data:
        return {"error": "No update data provided"}

    doc_ref = db.collection('questions').document(question_id)
    doc_ref.update(update_data)

    # If the question is answered, save it to the knowledge_base
    if update_data.get('status') == 'answered':
        question_data = doc_ref.get().to_dict()
        if question_data and 'question_text' in question_data and 'answer_text' in question_data:
            knowledge_base_ref = db.collection('knowledge_base').document(question_id)
            knowledge_base_ref.set({
                'question_text': question_data['question_text'],
                'answer_text': question_data['answer_text'],
                'timestamp': datetime.datetime.now(tz=datetime.timezone.utc)
            })

    return {"question_id": question_id, "status": update_data.get('status', 'updated')}

@app.get("/knowledge-base")
def get_knowledge_base():
    if not db:
        return {"error": "Database not initialized"}
    
    knowledge_ref = db.collection('knowledge_base').stream()
    
    knowledge_entries = []
    for entry in knowledge_ref:
        knowledge_entries.append(entry.to_dict())
            
    return {"knowledge_base": knowledge_entries}

@app.get("/learned-answers")
def get_learned_answers():
    if not db:
        return {"error": "Database not initialized"}
    
    questions_ref = db.collection('questions').where('status', '==', 'answered').stream()
    
    learned_answers = []
    for q in questions_ref:
        question_data = q.to_dict()
        # Ensure we only include questions that have an answer
        if 'question_text' in question_data and 'answer_text' in question_data:
            learned_answers.append({
                "question_text": question_data["question_text"],
                "answer_text": question_data["answer_text"],
            })
            
    return {"learned_answers": learned_answers}

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
