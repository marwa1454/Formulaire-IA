from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator
from typing import Optional, List
import mysql.connector
from fastapi.middleware.cors import CORSMiddleware
import logging
import json

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS for Live Server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:5501", "*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Pydantic model for form data
class FormData(BaseModel):
    question1: str
    question2: str
    question3: str
    question4: List[str]  # List of strings, validated to have at least one item
    question5: str
    question6: str
    question7: str
    question8: str
    question9: str
    question10: str
    question11: str
    question12: str
    question13: str
    question14: str
    question15: Optional[str] = None
    question16: Optional[str] = None
    other_sector: Optional[str] = None

    @validator('question1', 'question2', 'question3', 'question5', 'question6', 'question7', 'question8', 'question9', 'question10', 'question11', 'question12', 'question13', 'question14')
    def check_not_empty(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Ce champ ne peut pas être vide")
        return v

    @validator('question4')
    def check_question4_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("La question 4 doit contenir au moins une sélection")
        return v

    @validator('other_sector')
    def check_other_sector(cls, v, values):
        if values.get('question8') == "Autre" and (v is None or v.strip() == ""):
            raise ValueError("Le secteur personnalisé est requis lorsque 'Autre' est sélectionné pour la question 8")
        return v

# MySQL connection
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="db",
            user="root",
            password="mysecretpassword",
            database="formulaire_db"
        )
        logger.debug("Successfully connected to MySQL database")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Database connection failed: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(err)}")

@app.on_event("startup")
async def startup():
    logger.info("Starting up application and creating database table if not exists")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create table with all required columns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS responses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            question1 VARCHAR(255) NOT NULL,
            question2 VARCHAR(255) NOT NULL,
            question3 VARCHAR(255) NOT NULL,
            question4 TEXT NOT NULL,
            question5 VARCHAR(255) NOT NULL,
            question6 VARCHAR(255) NOT NULL,
            question7 VARCHAR(255) NOT NULL,
            question8 VARCHAR(255) NOT NULL,
            other_sector TEXT,
            question9 VARCHAR(255) NOT NULL,
            question10 VARCHAR(255) NOT NULL,
            question11 VARCHAR(255) NOT NULL,
            question12 VARCHAR(255) NOT NULL,
            question13 VARCHAR(255) NOT NULL,
            question14 VARCHAR(255) NOT NULL,
            question15 TEXT,
            question16 TEXT
        )
    ''')
    conn.commit()
    
    # Verify and add missing columns
    cursor.execute("DESCRIBE responses")
    existing_columns = [row[0] for row in cursor.fetchall()]
    logger.debug(f"Table responses columns: {existing_columns}")
    
    # Dictionary of required columns and their types
    required_columns = {
        'other_sector': 'TEXT',
        'question15': 'TEXT',
        'question16': 'TEXT'
    }
    
    # Check and add missing columns
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            try:
                logger.warning(f"Column '{column_name}' not found, attempting to add it")
                cursor.execute(f"ALTER TABLE responses ADD COLUMN {column_name} {column_type}")
                conn.commit()
                logger.info(f"Column '{column_name}' added successfully")
            except mysql.connector.Error as err:
                logger.error(f"Failed to add column '{column_name}': {str(err)}")
                # Continue with other columns even if one fails
    
    # Final verification
    cursor.execute("DESCRIBE responses")
    final_columns = [row[0] for row in cursor.fetchall()]
    logger.info(f"Final table structure: {final_columns}")
    
    cursor.close()
    conn.close()
    logger.info("Database table created or verified")

@app.post("/submit")
async def submit_form(data: FormData):
    logger.debug(f"Received form data: {data.dict()}")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Convert question4 list to JSON string
        question4_value = json.dumps(data.question4)
        # Use other_sector if question8 is "Autre"
        question8_value = data.other_sector if data.question8 == "Autre" else data.question8
        
        cursor.execute('''
            INSERT INTO responses (
                question1, question2, question3, question4, question5,
                question6, question7, question8, other_sector, question9,
                question10, question11, question12, question13, question14,
                question15, question16
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data.question1, data.question2, data.question3, question4_value,
            data.question5, data.question6, data.question7, question8_value,
            data.other_sector, data.question9, data.question10, data.question11,
            data.question12, data.question13, data.question14, data.question15,
            data.question16
        ))
        conn.commit()
        logger.info("Data successfully inserted into database")
        return {
            "message": "Le questionnaire est désormais terminé\nLes résultats sont en cours de traitement et vous seront communiqués par projection à l'écran dans un court instant...\n\nNous vous remercions pour votre participation et vous souhaitons une agréable fin de journée!"
        }
    except mysql.connector.Error as err:
        logger.error(f"Database insertion failed: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(err)}")
    finally:
        cursor.close()
        conn.close()

@app.get("/responses")
async def get_all_responses():
    logger.debug("Fetching all responses from database")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM responses")
        responses = cursor.fetchall()
        for response in responses:
            if response['question4']:
                try:
                    response['question4'] = json.loads(response['question4'])
                except json.JSONDecodeError:
                    response['question4'] = []
        logger.info(f"Fetched {len(responses)} responses")
        return {"message": responses}
    except mysql.connector.Error as err:
        logger.error(f"Failed to fetch responses: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch responses: {str(err)}")
    finally:
        cursor.close()
        conn.close()

# Optional: Debug endpoint to check table structure
@app.get("/debug/table-structure")
async def get_table_structure():
    """Debug endpoint to check the current table structure"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DESCRIBE responses")
        columns = cursor.fetchall()
        return {"table_structure": columns}
    except mysql.connector.Error as err:
        logger.error(f"Failed to get table structure: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(err)}")
    finally:
        cursor.close()
        conn.close()