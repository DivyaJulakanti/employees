from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr
from typing import List
from datetime import date, datetime
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import re

app = FastAPI()

# MySQL connection
DATABASE_URL = "mysql+pymysql://root:root@localhost:3306/mydatabase"
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this to certain domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# SQLAlchemy Models
class EmployeePersonalInfo(Base):
    __tablename__ = "employee_personal_info"
    employee_id = Column(String(20), primary_key=True, unique=True, nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    gender = Column(String(10), nullable=False)
    mobileno = Column(String(15), unique=True, nullable=False)
    address = Column(String(200), nullable=False)

    employment = relationship("EmployeeEmploymentInfo", back_populates="personal", uselist=False)

class EmployeeEmploymentInfo(Base):
    __tablename__ = "employee_employment_info"
    employee_id = Column(String(20), ForeignKey("employee_personal_info.employee_id"), primary_key=True)
    email = Column(String(100), unique=True, nullable=False)
    dob = Column(Date, nullable=False)
    joiningdate = Column(Date, nullable=False)

    personal = relationship("EmployeePersonalInfo", back_populates="employment")

Base.metadata.create_all(bind=engine)

# Pydantic Model
class Employee(BaseModel):
    first_name: str
    last_name: str
    gender: str
    dob: date
    mobileno: int
    email: EmailStr
    address: str
    employee_id: str
    joiningdate: date

# Render HTML form
@app.get("/form", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

# Render employeelist.html
@app.get("/", response_class=HTMLResponse)
async def get_employees(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(EmployeePersonalInfo, EmployeeEmploymentInfo)
          .join(EmployeeEmploymentInfo, EmployeePersonalInfo.employee_id == EmployeeEmploymentInfo.employee_id)
          .all()
    )

    result = []
    for personal, employment in rows:
        result.append({
            "employee_id": personal.employee_id,
            "first_name": personal.first_name,
            "last_name": personal.last_name,
            "gender": personal.gender,
            "dob": str(employment.dob),
            "mobileno": personal.mobileno,
            "email": employment.email,
            "address": personal.address,
            "joiningdate": str(employment.joiningdate)
        })

    return templates.TemplateResponse("employeelist.html", {"request": request, "employees": result})

# Get all employee data in JSON
@app.get("/employees")
async def get_employees_data(db: Session = Depends(get_db)):
    rows = (
        db.query(EmployeePersonalInfo, EmployeeEmploymentInfo)
          .join(EmployeeEmploymentInfo, EmployeePersonalInfo.employee_id == EmployeeEmploymentInfo.employee_id)
          .all()
    )

    result = []
    for personal, employment in rows:
        result.append({
            "employee_id": personal.employee_id,
            "first_name": personal.first_name,
            "last_name": personal.last_name,
            "gender": personal.gender,
            "mobileno": personal.mobileno,
            "address": personal.address,
            "email": employment.email,
            "dob": employment.dob.isoformat(),
            "joiningdate": employment.joiningdate.isoformat()
        })
    return result

# Add new employee
@app.post("/employees")
async def add_employee(employee: Employee, db: Session = Depends(get_db)):

    # Validation
    if not re.fullmatch(r"^[A-Za-z]+$", employee.first_name):
        return JSONResponse(status_code=400, content={"detail": "First name must contain only letters"})

    if not re.fullmatch(r"^[A-Za-z]+$", employee.last_name):
        return JSONResponse(status_code=400, content={"detail": "Last name must contain only letters"})

    if employee.gender not in ["Male", "Female", "Other"]:
        return JSONResponse(status_code=400, content={"detail": "Invalid gender"})

    if not (1000000000 <= employee.mobileno <= 9999999999):
        return JSONResponse(status_code=400, content={"detail": "Invalid mobile number"})

    if not employee.address or len(employee.address.strip()) < 5:
        return JSONResponse(status_code=400, content={"detail": "Address too short"})

    if not re.fullmatch(r"^[A-Za-z0-9]{3,15}$", employee.employee_id):
        return JSONResponse(status_code=400, content={"detail": "Invalid employee ID"})

    today = date.today()
    age = today.year - employee.dob.year - ((today.month, today.day) < (employee.dob.month, employee.dob.day))

    if employee.dob > today or age < 18:
        return JSONResponse(status_code=400, content={"detail": "Employee must be at least 18 years old"})

    # Check for duplicates
    if db.query(EmployeePersonalInfo).filter_by(employee_id=employee.employee_id).first():
        return JSONResponse(status_code=409, content={"detail": "Employee ID already exists"})

    if db.query(EmployeePersonalInfo).filter_by(mobileno=str(employee.mobileno)).first():
        return JSONResponse(status_code=409, content={"detail": "Mobile number already exists"})

    if db.query(EmployeeEmploymentInfo).filter_by(email=employee.email).first():
        return JSONResponse(status_code=409, content={"detail": "Email already exists"})

    try:
        # Insert into personal info
        personal = EmployeePersonalInfo(
            employee_id=employee.employee_id,
            first_name=employee.first_name,
            last_name=employee.last_name,
            gender=employee.gender,
            mobileno=str(employee.mobileno),
            address=employee.address
        )
        db.add(personal)

        # Insert into employment info
        employment = EmployeeEmploymentInfo(
            employee_id=employee.employee_id,
            email=employee.email,
            dob=employee.dob,
            joiningdate=employee.joiningdate
        )
        db.add(employment)

        db.commit()
        return JSONResponse(status_code=201, content={"message": "Employee added successfully"})

    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"detail": f"Database error: {str(e)}"})
