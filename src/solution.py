from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

users = {}
todos = {}

security = HTTPBasic()

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

class ItemRequest(BaseModel):
    item: str = Field(..., min_length=1)

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    username = credentials.username
    if username not in users:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"}
        )
    if not pwd_context.verify(credentials.password, users[username]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"}
        )
    return username

@app.post("/register")
async def register(request: RegisterRequest):
    if request.username in users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    hashed_password = pwd_context.hash(request.password)
    users[request.username] = hashed_password
    todos[request.username] = []
    return {"message": "User registered successfully"}

@app.get("/items/")
async def get_items(username: str = Depends(get_current_username)):
    return {"items": todos[username]}

@app.post("/items/")
async def add_item(item: ItemRequest, username: str = Depends(get_current_username)):
    todos[username].append(item.item)
    return {"items": todos[username]}