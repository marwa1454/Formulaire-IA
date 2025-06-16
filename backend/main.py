from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, validator
from typing import Optional, List
import mysql.connector
from fastapi.middleware.cors import CORSMiddleware
import logging
import json
import hashlib
import time

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
    browser_fingerprint: Optional[str] = None  # NOUVEAU: pour l'anti-doublon

    @validator('question1', 'question2', 'question3', 'question5', 'question6', 'question7', 'question8', 'question9', 'question10', 'question11', 'question12', 'question13', 'question14')
    def check_not_empty(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Ce champ ne peut pas être vide")
# Configuration pour le mode développeur
DEVELOPER_MODE = True  # Changez à False en production
DEVELOPER_IPS = ["127.0.0.1", "localhost", "::1"]  # IPs autorisées en mode dev

# Fonction pour vérifier si c'est un développeur
def is_developer(request: Request):
    """Vérifie si la requête vient d'un développeur"""
    if not DEVELOPER_MODE:
        return False
    
    client_ip = request.client.host
    return client_ip in DEVELOPER_IPS

# Fonction pour générer un hash d'IP et User-Agent
def generate_user_hash(request: Request):
    """Génère un hash unique basé sur l'IP et le User-Agent pour éviter les doublons"""
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "")
    
    # Créer un hash unique mais anonyme
    unique_string = f"{client_ip}:{user_agent}"
    return hashlib.sha256(unique_string.encode()).hexdigest()

# Fonction pour vérifier si l'utilisateur a déjà soumis
def check_duplicate_submission(conn, user_hash: str, browser_fingerprint: str = None):
    """Vérifie si l'utilisateur a déjà soumis le questionnaire"""
    cursor = conn.cursor()
    try:
        # Vérifier par hash d'IP/User-Agent
        cursor.execute("""
            SELECT COUNT(*) FROM responses 
            WHERE user_hash = %s AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """, (user_hash,))
        
        ip_count = cursor.fetchone()[0]
        
        # Vérifier par fingerprint navigateur si fourni
        fingerprint_count = 0
        if browser_fingerprint:
            cursor.execute("""
                SELECT COUNT(*) FROM responses 
                WHERE browser_fingerprint = %s AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """, (browser_fingerprint,))
            fingerprint_count = cursor.fetchone()[0]
        
        return ip_count > 0 or fingerprint_count > 0
        
    except mysql.connector.Error as err:
        logger.error(f"Error checking duplicate: {str(err)}")
        return False
    finally:
        cursor.close()

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
    
    # Create table with all required columns + timestamp + anti-duplicate fields
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
            question16 TEXT,
            user_hash VARCHAR(255),
            browser_fingerprint VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_hash (user_hash),
            INDEX idx_browser_fingerprint (browser_fingerprint),
            INDEX idx_created_at (created_at)
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
        'question16': 'TEXT',
        'user_hash': 'VARCHAR(255)',
        'browser_fingerprint': 'VARCHAR(255)',
        'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
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

# NOUVEAU: Endpoint pour les statistiques de progression (DASHBOARD)
@app.get("/progress")
async def get_progress():
    """API qui retourne les statistiques de progression en temps réel pour le dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Compter le total de réponses
        cursor.execute("SELECT COUNT(*) FROM responses")
        total_responses = cursor.fetchone()[0]
        
        # Compter les réponses des dernières 24h (si colonne created_at existe)
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM responses 
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """)
            responses_24h = cursor.fetchone()[0]
        except mysql.connector.Error:
            # Si la colonne created_at n'existe pas, utiliser le total
            responses_24h = total_responses
        
        # Compter les réponses de la dernière heure (si colonne created_at existe)
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM responses 
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            """)
            responses_1h = cursor.fetchone()[0]
        except mysql.connector.Error:
            # Si la colonne created_at n'existe pas, utiliser 0
            responses_1h = 0
        
        # Objectif configuré (vous pouvez modifier cette valeur selon vos besoins)
        target = 100
        percentage = min((total_responses / target) * 100, 100) if target > 0 else 0
        
        logger.info(f"Dashboard stats - Total: {total_responses}, 24h: {responses_24h}, 1h: {responses_1h}")
        
        return {
            "total_responses": total_responses,
            "target": target,
            "percentage": round(percentage, 1),
            "remaining": max(target - total_responses, 0),
            "completed": total_responses >= target,
            "responses_24h": responses_24h,
            "responses_1h": responses_1h,
            "timestamp": "now"
        }
    except mysql.connector.Error as err:
        logger.error(f"Failed to get progress: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(err)}")
    finally:
        cursor.close()
        conn.close()

@app.post("/submit")
async def submit_form(data: FormData, request: Request):
    logger.debug(f"Received form data: {data.dict()}")
    
    # Générer le hash utilisateur pour l'anti-doublon
    user_hash = generate_user_hash(request)
    client_ip = request.client.host
    
    # Vérifier si c'est un développeur
    if is_developer(request):
        logger.info(f"🔧 Developer mode: Skipping duplicate check for IP {client_ip}")
    else:
        # Vérifier les doublons AVANT l'insertion pour les utilisateurs normaux
        conn = get_db_connection()
        if check_duplicate_submission(conn, user_hash, data.browser_fingerprint):
            conn.close()
            logger.warning(f"Duplicate submission attempt from user_hash: {user_hash}")
            raise HTTPException(
                status_code=409, 
                detail="Vous avez déjà soumis ce questionnaire. Merci pour votre participation !"
            )
        conn.close()
    
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
                question15, question16, user_hash, browser_fingerprint
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data.question1, data.question2, data.question3, question4_value,
            data.question5, data.question6, data.question7, question8_value,
            data.other_sector, data.question9, data.question10, data.question11,
            data.question12, data.question13, data.question14, data.question15,
            data.question16, user_hash, data.browser_fingerprint
        ))
        conn.commit()
        
        dev_status = "👨‍💻 [DEV MODE]" if is_developer(request) else ""
        logger.info(f"Data successfully inserted {dev_status} with user_hash: {user_hash}")
        
        # Messages de fin personnalisés
        return {
            "success": True,
            "message": "Le questionnaire est désormais terminé",
            "details": "Les résultats sont en cours de traitement et vous seront communiqués par projection à l'écran dans un court instant...",
            "thanks": "Nous vous remercions pour votre participation et vous souhaitons une agréable fin de journée!"
        }
    except mysql.connector.Error as err:
        logger.error(f"Database insertion failed: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(err)}")
    finally:
        cursor.close()
        conn.close()

@app.get("/responses")
async def get_all_responses():
    """Endpoint pour récupérer toutes les réponses (pour analyse administrative)"""
    logger.debug("Fetching all responses from database")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM responses ORDER BY id DESC")
        responses = cursor.fetchall()
        
        # Parse question4 JSON pour chaque réponse
        for response in responses:
            if response['question4']:
                try:
                    response['question4'] = json.loads(response['question4'])
                except json.JSONDecodeError:
                    response['question4'] = []
        
        logger.info(f"Fetched {len(responses)} responses")
        return {"responses": responses, "total": len(responses)}
    except mysql.connector.Error as err:
        logger.error(f"Failed to fetch responses: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch responses: {str(err)}")
    finally:
        cursor.close()
        conn.close()

# NOUVEAU: Endpoint pour les statistiques détaillées
@app.get("/stats")
async def get_detailed_stats():
    """Endpoint pour récupérer des statistiques détaillées sur les réponses"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        stats = {}
        
        # Stats générales
        cursor.execute("SELECT COUNT(*) as total FROM responses")
        stats['total_responses'] = cursor.fetchone()['total']
        
        # Stats par secteur d'activité (question8)
        cursor.execute("""
            SELECT question8 as sector, COUNT(*) as count 
            FROM responses 
            GROUP BY question8 
            ORDER BY count DESC
        """)
        stats['by_sector'] = cursor.fetchall()
        
        # Stats par durée de possession du smartphone (question1)
        cursor.execute("""
            SELECT question1 as duration, COUNT(*) as count 
            FROM responses 
            GROUP BY question1 
            ORDER BY count DESC
        """)
        stats['smartphone_duration'] = cursor.fetchall()
        
        # Stats d'utilisation smartphone (question2)
        cursor.execute("""
            SELECT question2 as usage_type, COUNT(*) as count 
            FROM responses 
            GROUP BY question2 
            ORDER BY count DESC
        """)
        stats['usage_type'] = cursor.fetchall()
        
        # Stats des réponses par jour (si created_at existe)
        try:
            cursor.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count 
                FROM responses 
                WHERE created_at IS NOT NULL
                GROUP BY DATE(created_at) 
                ORDER BY date DESC 
                LIMIT 7
            """)
            stats['daily_responses'] = cursor.fetchall()
        except mysql.connector.Error:
            stats['daily_responses'] = []
        
        logger.info(f"Generated detailed stats for {stats['total_responses']} responses")
        return stats
        
    except mysql.connector.Error as err:
        logger.error(f"Failed to generate stats: {str(err)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(err)}")
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

# Health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)