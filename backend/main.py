from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any
import mysql.connector
from mysql.connector import pooling, Error as MySQLError
import logging
import json
import hashlib
import os
import asyncio
from datetime import datetime, timedelta
import time
from functools import wraps
import weakref
from contextlib import asynccontextmanager

# Configuration depuis variables d'environnement avec domaines de production
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_USER = os.getenv("DATABASE_USER", "root")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "")
DB_NAME = os.getenv("DATABASE_NAME", "formulaire_db")
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://127.0.0.1:5501", 
    "http://localhost:5500",
    "http://localhost:5501",
    "http://localhost:3000",
    "https://ia-perception.ansie.dj",
    "https://ia-perception-api.ansie.dj",
    "http://ia-perception.ansie.dj",
    "http://ia-perception-api.ansie.dj",
    "*"  # Pour développement - à retirer en production stricte
]
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
TARGET_RESPONSES = int(os.getenv("TARGET_RESPONSES", "200"))
MAX_POOL_SIZE = int(os.getenv("MAX_POOL_SIZE", "15"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Configuration logging optimisée pour la production
logging.basicConfig(
    level=logging.INFO if ENVIRONMENT == "production" else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('questionnaire_api.log') if os.getenv("LOG_TO_FILE", "true").lower() == "true" else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

# Pool de connexions global
connection_pool = None

# Cache simple en mémoire (sans dépendances externes)
simple_cache = {}
cache_timestamps = {}

def get_from_simple_cache(key: str, ttl: int = 10):
    """Cache simple sans Redis pour éviter les dépendances"""
    if key in simple_cache:
        if time.time() - cache_timestamps.get(key, 0) < ttl:
            return simple_cache[key]
        else:
            simple_cache.pop(key, None)
            cache_timestamps.pop(key, None)
    return None

def set_simple_cache(key: str, value: any, ttl: int = 10):
    """Définir une valeur dans le cache simple"""
    simple_cache[key] = value
    cache_timestamps[key] = time.time()

def clear_simple_cache():
    """Vider le cache simple"""
    simple_cache.clear()
    cache_timestamps.clear()

# Rate limiting en mémoire optimisé
class InMemoryRateLimit:
    def __init__(self):
        self.requests = {}
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
    
    def is_rate_limited(self, client_ip: str, max_requests: int = RATE_LIMIT_PER_MINUTE) -> bool:
        current_time = time.time()
        
        # Nettoyage périodique
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries()
            self.last_cleanup = current_time
        
        # Vérifier les requêtes pour cette IP
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # Supprimer les requêtes plus anciennes qu'une minute
        minute_ago = current_time - 60
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip] 
            if req_time > minute_ago
        ]
        
        # Vérifier si la limite est dépassée
        if len(self.requests[client_ip]) >= max_requests:
            return True
        
        # Ajouter cette requête
        self.requests[client_ip].append(current_time)
        return False
    
    def _cleanup_old_entries(self):
        current_time = time.time()
        minute_ago = current_time - 60
        
        for ip in list(self.requests.keys()):
            if ip in self.requests:
                self.requests[ip] = [
                    req_time for req_time in self.requests[ip] 
                    if req_time > minute_ago
                ]
                if not self.requests[ip]:
                    del self.requests[ip]

rate_limiter = InMemoryRateLimit()

# Configuration du pool de connexions avec retry et fallback
def create_connection_pool():
    global connection_pool
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Creating database connection pool (attempt {attempt + 1}/{max_retries})")
            logger.info(f"📋 Connection: host={DB_HOST}, user={DB_USER}, database={DB_NAME}")
            
            # Test connection first
            test_conn = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                connect_timeout=10,
                autocommit=False
            )
            
            # Test query
            cursor = test_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            test_conn.close()
            logger.info("✅ Test connection successful")
            
            # Create pool
            connection_pool = pooling.MySQLConnectionPool(
                pool_name="questionnaire_pool",
                pool_size=MAX_POOL_SIZE,
                pool_reset_session=True,
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                autocommit=False,
                connect_timeout=10,
                use_unicode=True
            )
            logger.info(f"✅ Database connection pool created with {MAX_POOL_SIZE} connections")
            return
            
        except mysql.connector.Error as e:
            logger.error(f"❌ Database connection attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("❌ All database connection attempts failed")
                raise
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"🚀 Starting Questionnaire IA API v2.2 - Environment: {ENVIRONMENT}")
    
    try:
        create_connection_pool()
        await initialize_database()
        logger.info("✅ Application startup completed successfully")
    except Exception as e:
        logger.error(f"❌ Application startup failed: {str(e)}")
        # Continue anyway to allow health checks
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down API")
    if connection_pool:
        try:
            connection_pool.close()
            logger.info("✅ Connection pool closed")
        except Exception as e:
            logger.error(f"❌ Error closing connection pool: {e}")

app = FastAPI(
    title="Questionnaire IA API",
    description="API pour questionnaire sur l'intelligence artificielle - Production Ready",
    version="2.2.0",
    lifespan=lifespan
)

# Middlewares
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Modèle Pydantic avec validation production
class FormData(BaseModel):
    question1: str = Field(..., min_length=1, max_length=255)
    question2: str = Field(..., min_length=1, max_length=255)
    question3: str = Field(..., min_length=1, max_length=255)
    question4: List[str] = Field(..., min_items=1, max_items=10)
    question5: str = Field(..., min_length=1, max_length=255)
    question6: str = Field(..., min_length=1, max_length=255)
    question7: str = Field(..., min_length=1, max_length=255)
    question8: str = Field(..., min_length=1, max_length=255)
    question9: str = Field(..., min_length=1, max_length=500)
    question10: str = Field(..., min_length=1, max_length=500)
    question11: str = Field(..., min_length=1, max_length=10)
    question12: str = Field(..., min_length=1, max_length=50)
    question13: str = Field(..., min_length=1, max_length=500)
    question14: str = Field(..., min_length=1, max_length=500)
    question15: Optional[str] = Field(None, max_length=300)
    question16: Optional[str] = Field(None, max_length=300)
    other_sector: Optional[str] = Field(None, max_length=255)
    browser_fingerprint: Optional[str] = Field(None, max_length=255)
    submission_timestamp: Optional[str] = Field(None, max_length=50)
    user_agent: Optional[str] = Field(None, max_length=500)
    screen_resolution: Optional[str] = Field(None, max_length=20)

    @validator('question1', 'question2', 'question3', 'question5', 'question6', 'question7', 'question8', 'question9', 'question10', 'question11', 'question12', 'question13', 'question14')
    def check_not_empty(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Ce champ ne peut pas être vide")
        return v.strip()

    @validator('question4')
    def check_question4_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("La question 4 doit contenir au moins une sélection")
        # Éviter les doublons
        unique_values = list(set(v))
        if len(unique_values) != len(v):
            return unique_values  # Nettoyer automatiquement
        return v

    @validator('other_sector')
    def check_other_sector(cls, v, values):
        question8 = values.get('question8', '')
        if question8 == "Autre" and (v is None or (isinstance(v, str) and v.strip() == "")):
            if ENVIRONMENT == "production":
                raise ValueError("Le secteur personnalisé est requis lorsque 'Autre' est sélectionné")
            else:
                logger.warning("⚠️ Other sector required but not provided (dev mode)")
        return v.strip() if v else v

    @validator('question15', 'question16')
    def check_word_limit(cls, v):
        if v and v.strip():
            words = v.strip().split()
            word_count = len([word for word in words if word.strip()])
            if word_count > 30:
                if ENVIRONMENT == "production":
                    raise ValueError(f"Maximum 30 mots autorisés, vous en avez {word_count}")
                else:
                    logger.warning(f"⚠️ Word limit exceeded: {word_count} words (dev mode)")
        return v.strip() if v else None

    @validator('browser_fingerprint')
    def validate_fingerprint(cls, v):
        if v and len(v) > 255:
            return v[:255]
        return v

# Configuration développeur
DEVELOPER_MODE = os.getenv("DEVELOPER_MODE", "true" if ENVIRONMENT != "production" else "false").lower() == "true"
DEVELOPER_IPS = ["127.0.0.1", "localhost", "::1", "192.168.1.1"]

def is_developer(request: Request):
    if not DEVELOPER_MODE:
        return False
    client_ip = request.client.host
    return client_ip in DEVELOPER_IPS or client_ip.startswith("192.168.") or client_ip.startswith("10.")

def generate_user_hash(request: Request):
    try:
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "unknown")
        forwarded_for = request.headers.get("x-forwarded-for", "")
        
        real_ip = forwarded_for.split(',')[0].strip() if forwarded_for else client_ip
        unique_string = f"{real_ip}:{user_agent}:{datetime.now().strftime('%Y-%m-%d')}"
        return hashlib.sha256(unique_string.encode()).hexdigest()
    except Exception as e:
        logger.error(f"Error generating user hash: {str(e)}")
        return f"fallback_{int(time.time())}"

def check_duplicate_submission(conn, user_hash: str, browser_fingerprint: str = None):
    if not conn:
        return False
        
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Vérification par hash utilisateur
        cursor.execute("""
            SELECT COUNT(*) FROM responses 
            WHERE user_hash = %s AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """, (user_hash,))
        result = cursor.fetchone()
        ip_count = result[0] if result else 0
        
        # Vérification par fingerprint si disponible
        fingerprint_count = 0
        if browser_fingerprint:
            cursor.execute("""
                SELECT COUNT(*) FROM responses 
                WHERE browser_fingerprint = %s AND created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """, (browser_fingerprint,))
            result = cursor.fetchone()
            fingerprint_count = result[0] if result else 0
        
        return ip_count > 0 or fingerprint_count > 0
        
    except MySQLError as err:
        logger.error(f"Error checking duplicate: {str(err)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking duplicate: {str(e)}")
        return False
    finally:
        if cursor:
            cursor.close()

def get_db_connection():
    try:
        if connection_pool:
            conn = connection_pool.get_connection()
            if conn.is_connected():
                return conn
        
        # Fallback connection
        logger.warning("⚠️ Using fallback connection (pool not available)")
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci',
            autocommit=False,
            connect_timeout=10
        )
        return conn
        
    except MySQLError as err:
        logger.error(f"Database connection failed: {str(err)}")
        raise HTTPException(status_code=500, detail="Service temporairement indisponible")
    except Exception as e:
        logger.error(f"Unexpected database error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")

async def initialize_database():
    logger.info("🔧 Initializing database...")
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Créer la base de données si elle n'existe pas
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
            cursor.execute(f"USE {DB_NAME}")
            
            # Créer la table avec structure optimisée
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS responses (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    question1 VARCHAR(255) NOT NULL,
                    question2 VARCHAR(255) NOT NULL,
                    question3 VARCHAR(255) NOT NULL,
                    question4 JSON,
                    question5 VARCHAR(255) NOT NULL,
                    question6 VARCHAR(255) NOT NULL,
                    question7 VARCHAR(255) NOT NULL,
                    question8 VARCHAR(255) NOT NULL,
                    other_sector TEXT,
                    question9 TEXT NOT NULL,
                    question10 TEXT NOT NULL,
                    question11 VARCHAR(10) NOT NULL,
                    question12 VARCHAR(50) NOT NULL,
                    question13 TEXT NOT NULL,
                    question14 TEXT NOT NULL,
                    question15 TEXT,
                    question16 TEXT,
                    user_hash VARCHAR(255),
                    browser_fingerprint VARCHAR(255),
                    submission_timestamp VARCHAR(50),
                    user_agent TEXT,
                    screen_resolution VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    
                    INDEX idx_user_hash (user_hash),
                    INDEX idx_browser_fingerprint (browser_fingerprint),
                    INDEX idx_created_at (created_at),
                    INDEX idx_submission_day (DATE(created_at))
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            ''')
            
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("✅ Database initialization completed")
            return
            
        except Exception as e:
            logger.error(f"❌ Database initialization attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                if ENVIRONMENT == "production":
                    raise
                else:
                    logger.warning("⚠️ Database initialization failed in dev mode - continuing anyway")

# Rate limiting avec exemptions pour développeurs
def rate_limit_check(request: Request):
    if ENVIRONMENT == "development" or is_developer(request):
        return
        
    client_ip = request.client.host
    if rate_limiter.is_rate_limited(client_ip, RATE_LIMIT_PER_MINUTE):
        raise HTTPException(
            status_code=429,
            detail=f"Trop de requêtes. Limite: {RATE_LIMIT_PER_MINUTE} requêtes par minute."
        )

# === ENDPOINTS ===

@app.get("/health")
async def health_check():
    """Endpoint de vérification de l'état du service"""
    try:
        db_status = "unknown"
        db_error = None
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            db_status = "connected"
        except Exception as e:
            db_status = "error"
            db_error = str(e)
            logger.error(f"Health check DB error: {e}")
        
        return {
            "status": "healthy" if db_status == "connected" else "degraded",
            "database": {
                "status": db_status,
                "error": db_error if db_status == "error" else None
            },
            "environment": ENVIRONMENT,
            "pool_size": MAX_POOL_SIZE,
            "target_responses": TARGET_RESPONSES,
            "developer_mode": DEVELOPER_MODE,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/count")
async def get_count():
    """Endpoint optimisé pour le compteur temps réel du dashboard"""
    try:
        # Vérifier le cache d'abord
        cached_count = get_from_simple_cache("total_count", ttl=3)
        if cached_count is not None:
            return {
                "count": cached_count,
                "cached": True,
                "timestamp": datetime.now().isoformat()
            }
        
        # Requête DB si pas en cache
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM responses")
        result = cursor.fetchone()
        count = result[0] if result else 0
        
        cursor.close()
        conn.close()
        
        # Cache pour 3 secondes
        set_simple_cache("total_count", count, ttl=3)
        
        return {
            "count": count,
            "cached": False,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get count: {str(e)}")
        # Retourner 0 au lieu d'une erreur pour le dashboard
        return {
            "count": 0,
            "error": True,
            "message": "Erreur temporaire",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/responses/{response_id}")
async def get_response_by_id(response_id: int):
    """Récupérer une réponse spécifique par ID"""
    try:
        if response_id <= 0:
            raise HTTPException(status_code=400, detail="ID de réponse invalide")
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                id, question1, question2, question3, question4, question5,
                question6, question7, question8, other_sector, question9,
                question10, question11, question12, question13, question14,
                question15, question16, created_at, updated_at
            FROM responses 
            WHERE id = %s
        """, (response_id,))
        
        response = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not response:
            raise HTTPException(status_code=404, detail="Réponse non trouvée")
        
        # Traitement des données JSON et dates
        if response['question4']:
            try:
                response['question4'] = json.loads(response['question4'])
            except json.JSONDecodeError:
                response['question4'] = []
        
        if response.get('created_at'):
            response['created_at'] = response['created_at'].isoformat()
        if response.get('updated_at'):
            response['updated_at'] = response['updated_at'].isoformat()
        
        return {
            "success": True,
            "response": response,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch response {response_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération")

@app.get("/progress")
async def get_progress():
    """Statistiques de progression avec cache"""
    try:
        # Vérifier le cache
        cached_progress = get_from_simple_cache("progress_stats", ttl=10)
        if cached_progress:
            return cached_progress
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_responses,
                COUNT(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 END) as responses_24h,
                COUNT(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as responses_1h
            FROM responses
        """)
        
        result = cursor.fetchone()
        total_responses, responses_24h, responses_1h = result if result else (0, 0, 0)
        
        target = TARGET_RESPONSES
        percentage = min((total_responses / target) * 100, 100) if target > 0 else 0
        
        cursor.close()
        conn.close()
        
        progress_data = {
            "total_responses": total_responses,
            "target": target,
            "percentage": round(percentage, 1),
            "remaining": max(target - total_responses, 0),
            "completed": total_responses >= target,
            "responses_24h": responses_24h,
            "responses_1h": responses_1h,
            "timestamp": datetime.now().isoformat()
        }
        
        # Cache pour 10 secondes
        set_simple_cache("progress_stats", progress_data, ttl=10)
        
        return progress_data
    except Exception as e:
        logger.error(f"Failed to get progress: {str(e)}")
        # Retourner valeurs par défaut au lieu d'erreur
        return {
            "total_responses": 0,
            "target": TARGET_RESPONSES,
            "percentage": 0,
            "remaining": TARGET_RESPONSES,
            "completed": False,
            "responses_24h": 0,
            "responses_1h": 0,
            "error": True,
            "timestamp": datetime.now().isoformat()
        }

@app.post("/submit")
async def submit_form(data: FormData, request: Request, _: None = Depends(rate_limit_check)):
    """Endpoint principal de soumission du questionnaire"""
    start_time = time.time()
    client_ip = request.client.host
    
    logger.info(f"📥 Form submission from {client_ip}")
    
    user_hash = generate_user_hash(request)
    
    # Vérification des doublons (sauf développeurs)
    if not is_developer(request) and ENVIRONMENT == "production":
        try:
            conn = get_db_connection()
            if check_duplicate_submission(conn, user_hash, data.browser_fingerprint):
                conn.close()
                logger.warning(f"🚫 Duplicate submission from {client_ip}")
                raise HTTPException(
                    status_code=409, 
                    detail="Vous avez déjà soumis ce questionnaire aujourd'hui. Merci pour votre participation !"
                )
            conn.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking duplicates: {str(e)}")
    else:
        logger.info(f"🔧 Skipping duplicate check for {client_ip} (dev mode)")
    
    # Insertion des données avec gestion d'erreurs robuste
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Préparation des données
        question4_value = json.dumps(data.question4, ensure_ascii=False)
        question8_value = data.other_sector if data.question8 == "Autre" and data.other_sector else data.question8
        
        logger.debug(f"💾 Inserting data for user_hash={user_hash[:8]}...")
        
        insert_query = '''
            INSERT INTO responses (
                question1, question2, question3, question4, question5,
                question6, question7, question8, other_sector, question9,
                question10, question11, question12, question13, question14,
                question15, question16, user_hash, browser_fingerprint,
                submission_timestamp, user_agent, screen_resolution
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        
        values = (
            data.question1, data.question2, data.question3, question4_value,
            data.question5, data.question6, data.question7, question8_value,
            data.other_sector, data.question9, data.question10, data.question11,
            data.question12, data.question13, data.question14, data.question15,
            data.question16, user_hash, data.browser_fingerprint,
            data.submission_timestamp, data.user_agent, data.screen_resolution
        )
        
        cursor.execute(insert_query, values)
        conn.commit()
        
        response_id = cursor.lastrowid
        
        # Vider les caches après insertion réussie
        clear_simple_cache()
        
        processing_time = round((time.time() - start_time) * 1000, 2)
        dev_status = " [DEV]" if is_developer(request) else ""
        logger.info(f"✅ Data inserted{dev_status} - ID: {response_id} - {processing_time}ms")
        
        return {
            "success": True,
            "message": "Le questionnaire est désormais terminé",
            "details": "Les résultats sont en cours de traitement et vous seront communiqués par projection à l'écran dans un court instant...",
            "thanks": "Nous vous remercions pour votre participation et vous souhaitons une agréable fin de journée!",
            "id": response_id,
            "processing_time_ms": processing_time
        }
        
    except mysql.connector.IntegrityError as err:
        logger.error(f"❌ Database integrity error: {str(err)}")
        if "Duplicate entry" in str(err) or "idx_unique_submission" in str(err):
            raise HTTPException(status_code=409, detail="Vous avez déjà soumis ce questionnaire aujourd'hui.")
        else:
            raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement")
    except MySQLError as err:
        logger.error(f"❌ Database insertion failed: {str(err)}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

@app.get("/responses")
async def get_all_responses(
    skip: int = Query(0, ge=0, description="Nombre d'éléments à ignorer"),
    limit: int = Query(100, ge=1, le=1000, description="Nombre maximum d'éléments à retourner")
):
    """
    Endpoint pour récupérer toutes les réponses avec pagination
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Requête optimisée avec pagination
        cursor.execute("""
            SELECT 
                id, question1, question2, question3, question4, question5,
                question6, question7, question8, other_sector, question9,
                question10, question11, question12, question13, question14,
                question15, question16, created_at, updated_at
            FROM responses 
            ORDER BY created_at DESC 
            LIMIT %s OFFSET %s
        """, (limit, skip))
        responses = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM responses")
        total = cursor.fetchone()['total']
        
        # Traitement des données JSON et dates
        for response in responses:
            if response['question4']:
                try:
                    response['question4'] = json.loads(response['question4'])
                except json.JSONDecodeError:
                    response['question4'] = []
            
            if response.get('created_at'):
                response['created_at'] = response['created_at'].isoformat()
            if response.get('updated_at'):
                response['updated_at'] = response['updated_at'].isoformat()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "responses": responses,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to fetch responses: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération")

@app.get("/stats")
async def get_detailed_stats():
    try:
        # Vérifier le cache d'abord
        cached_stats = get_from_cache("detailed_stats")
        if cached_stats:
            return cached_stats
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        stats = {}
        
        # Statistiques générales
        cursor.execute("SELECT COUNT(*) as total FROM responses")
        stats['total_responses'] = cursor.fetchone()['total']
        
        # Statistiques par secteur (top 20)
        cursor.execute("""
            SELECT question8 as sector, COUNT(*) as count 
            FROM responses 
            GROUP BY question8 
            ORDER BY count DESC
            LIMIT 20
        """)
        stats['by_sector'] = cursor.fetchall()
        
        # Durée de possession du smartphone
        cursor.execute("""
            SELECT question1 as duration, COUNT(*) as count 
            FROM responses 
            GROUP BY question1 
            ORDER BY count DESC
        """)
        stats['smartphone_duration'] = cursor.fetchall()
        
        # Réponses par jour (7 derniers jours)
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM responses 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY DATE(created_at) 
            ORDER BY date DESC
        """)
        daily_responses = cursor.fetchall()
        
        # Conversion des dates
        for item in daily_responses:
            if item['date']:
                item['date'] = item['date'].isoformat()
        
        stats['daily_responses'] = daily_responses
        
        # Statistiques de performance
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as last_hour,
                COUNT(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY) THEN 1 END) as last_day,
                COUNT(CASE WHEN created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) THEN 1 END) as last_week
            FROM responses
        """)
        perf_stats = cursor.fetchone()
        stats['performance'] = perf_stats
        
        # Statistiques sur les questions IA
        cursor.execute("""
            SELECT question9 as answer, COUNT(*) as count 
            FROM responses 
            GROUP BY question9 
            ORDER BY count DESC
        """)
        stats['ia_definition'] = cursor.fetchall()
        
        cursor.execute("""
            SELECT question12 as country, COUNT(*) as count 
            FROM responses 
            GROUP BY question12 
            ORDER BY count DESC
        """)
        stats['ia_investment_by_country'] = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        stats['timestamp'] = datetime.now().isoformat()
        
        # Mettre en cache pour 30 secondes
        set_cache("detailed_stats", stats, ttl=30)
        
        return stats
    except Exception as e:
        logger.error(f"Failed to generate stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la génération des statistiques")

@app.get("/responses/latest")
async def get_latest_responses(limit: int = Query(10, ge=1, le=50, description="Nombre de réponses récentes")):
    """
    Endpoint pour récupérer les dernières réponses soumises
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                id, question1, question8, created_at
            FROM responses 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (limit,))
        responses = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Conversion des dates
        for response in responses:
            if response.get('created_at'):
                response['created_at'] = response['created_at'].isoformat()
        
        return {
            "success": True,
            "latest_responses": responses,
            "count": len(responses),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to fetch latest responses: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération des dernières réponses")

@app.get("/responses/search")
async def search_responses(
    sector: Optional[str] = Query(None, description="Filtrer par secteur d'activité"),
    smartphone_duration: Optional[str] = Query(None, description="Filtrer par durée de possession du smartphone"),
    date_from: Optional[str] = Query(None, description="Date de début (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Date de fin (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """
    Endpoint pour rechercher et filtrer les réponses
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Construction de la requête dynamique
        where_conditions = []
        params = []
        
        if sector:
            where_conditions.append("question8 LIKE %s")
            params.append(f"%{sector}%")
        
        if smartphone_duration:
            where_conditions.append("question1 = %s")
            params.append(smartphone_duration)
        
        if date_from:
            where_conditions.append("DATE(created_at) >= %s")
            params.append(date_from)
        
        if date_to:
            where_conditions.append("DATE(created_at) <= %s")
            params.append(date_to)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # Requête pour compter le total
        count_query = f"SELECT COUNT(*) as total FROM responses WHERE {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()['total']
        
        # Requête pour les données avec pagination
        data_query = f"""
            SELECT 
                id, question1, question2, question3, question4, question5,
                question6, question7, question8, other_sector, question9,
                question10, question11, question12, question13, question14,
                question15, question16, created_at, updated_at
            FROM responses 
            WHERE {where_clause}
            ORDER BY created_at DESC 
            LIMIT %s OFFSET %s
        """
        
        params.extend([limit, skip])
        cursor.execute(data_query, params)
        responses = cursor.fetchall()
        
        # Traitement des données
        for response in responses:
            if response['question4']:
                try:
                    response['question4'] = json.loads(response['question4'])
                except json.JSONDecodeError:
                    response['question4'] = []
            
            if response.get('created_at'):
                response['created_at'] = response['created_at'].isoformat()
            if response.get('updated_at'):
                response['updated_at'] = response['updated_at'].isoformat()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "responses": responses,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total,
            "filters": {
                "sector": sector,
                "smartphone_duration": smartphone_duration,
                "date_from": date_from,
                "date_to": date_to
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to search responses: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la recherche")

@app.get("/export/csv")
async def export_responses_csv(
    sector: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    """
    Endpoint pour exporter les réponses en format CSV
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Construction de la requête avec filtres
        where_conditions = []
        params = []
        
        if sector:
            where_conditions.append("question8 LIKE %s")
            params.append(f"%{sector}%")
        
        if date_from:
            where_conditions.append("DATE(created_at) >= %s")
            params.append(date_from)
        
        if date_to:
            where_conditions.append("DATE(created_at) <= %s")
            params.append(date_to)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
            SELECT 
                id, question1, question2, question3, question4, question5,
                question6, question7, question8, other_sector, question9,
                question10, question11, question12, question13, question14,
                question15, question16, created_at
            FROM responses 
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT 10000
        """
        
        cursor.execute(query, params)
        responses = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Traitement pour CSV
        csv_data = []
        for response in responses:
            # Convertir question4 (JSON) en string
            if response['question4']:
                try:
                    q4_data = json.loads(response['question4'])
                    response['question4'] = '; '.join(q4_data) if isinstance(q4_data, list) else str(q4_data)
                except json.JSONDecodeError:
                    response['question4'] = ''
            
            # Convertir les dates
            if response.get('created_at'):
                response['created_at'] = response['created_at'].isoformat()
            
            csv_data.append(response)
        
        return {
            "success": True,
            "data": csv_data,
            "count": len(csv_data),
            "headers": [
                "id", "question1", "question2", "question3", "question4", "question5",
                "question6", "question7", "question8", "other_sector", "question9",
                "question10", "question11", "question12", "question13", "question14",
                "question15", "question16", "created_at"
            ],
            "filters": {
                "sector": sector,
                "date_from": date_from,
                "date_to": date_to
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to export CSV: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'export CSV")

@app.get("/monitoring")
async def get_monitoring_info():
    """
    Endpoint de monitoring pour vérifier la charge du système
    """
    try:
        # Informations sur le pool de connexions
        active_connections = 0
        pool_status = "unknown"
        
        if connection_pool:
            try:
                # Estimation du nombre de connexions actives
                active_connections = MAX_POOL_SIZE - connection_pool._cnx_pool.qsize()
                pool_status = "healthy"
            except Exception as e:
                pool_status = f"error: {str(e)}"
        
        # Test de connexion à la base de données
        db_status = "unknown"
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"
        
        # Statut Redis
        redis_status = "disabled"
        if redis_client:
            try:
                redis_client.ping()
                redis_status = "connected"
            except Exception as e:
                redis_status = f"error: {str(e)}"
        
        # Statistiques des caches
        cache_stats = {
            "stats_cache_size": len(stats_cache),
            "count_cache_size": len(count_cache),
            "stats_cache_hits": getattr(stats_cache, 'hits', 0),
            "stats_cache_misses": getattr(stats_cache, 'misses', 0)
        }
        
        return {
            "status": "operational",
            "database": {
                "status": db_status,
                "active_connections": active_connections,
                "max_connections": MAX_POOL_SIZE,
                "pool_status": pool_status
            },
            "redis": {
                "status": redis_status
            },
            "cache": cache_stats,
            "rate_limiting": {
                "limit_per_minute": RATE_LIMIT_PER_MINUTE,
                "active_ips": len(rate_limiter.requests)
            },
            "configuration": {
                "target_responses": TARGET_RESPONSES,
                "developer_mode": DEVELOPER_MODE,
                "environment": ENVIRONMENT
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Monitoring failed: {str(e)}")
        return {
            "status": "error", 
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/admin/clear-cache")
async def clear_cache():
    """
    Endpoint admin pour vider les caches
    """
    try:
        # Vider les caches en mémoire
        stats_cache.clear()
        count_cache.clear()
        
        # Vider Redis si disponible
        cache_cleared = {"memory": True, "redis": False}
        if redis_client:
            try:
                redis_client.flushdb()
                cache_cleared["redis"] = True
            except Exception as e:
                logger.warning(f"Failed to clear Redis cache: {e}")
        
        return {
            "success": True,
            "message": "Cache vidé avec succès",
            "cleared": cache_cleared,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to clear cache: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors du vidage du cache")

# Gestion des erreurs globales
@app.exception_handler(MySQLError)
async def mysql_exception_handler(request: Request, exc: MySQLError):
    logger.error(f"MySQL Error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Erreur de base de données",
            "message": "Une erreur technique est survenue. Veuillez réessayer.",
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Erreur interne",
            "message": "Une erreur inattendue est survenue.",
            "timestamp": datetime.now().isoformat()
        }
    )

if __name__ == "__main__":
    import uvicorn
    
    # Configuration optimisée pour la production
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        log_level="info",
        workers=1,  # Une seule instance avec pool de connexions
        access_log=True,
        server_header=False,  # Sécurité
        date_header=False     # Sécurité
    )





