# 🚔 KSP Crime Intelligence Platform

An AI-powered Crime Intelligence Platform built for Karnataka State Police to visualize crime patterns, detect hotspots, analyze criminal networks, and predict future crime risk using GIS and Machine Learning.

---

# 📸 Project Demo

## Dashboard
<img width="1918" height="862" alt="Screenshot 2026-07-19 215313" src="https://github.com/user-attachments/assets/3bd0ad37-f97e-48a5-a45d-59ea27ebba82" />


## Crime Heatmap
<img width="1918" height="868" alt="Screenshot 2026-07-19 215348" src="https://github.com/user-attachments/assets/6c0cc31d-3997-43f6-b0d5-cc7f270fbcb4" />


## Criminal Network Analysis
<img width="1917" height="861" alt="Screenshot 2026-07-19 215403" src="https://github.com/user-attachments/assets/f65547e7-d6d9-4007-a3ce-6259fb5c3d8d" />


## Risk Prediction Dashboard
<img width="1918" height="861" alt="Screenshot 2026-07-19 215417" src="https://github.com/user-attachments/assets/e490b821-ef35-45f5-965d-2a6b017e19d1" />


## Ground Truth Recovery
<img width="1918" height="870" alt="Screenshot 2026-07-19 215425" src="https://github.com/user-attachments/assets/0a48b525-e259-48a3-8cab-b2da9bb74065" />


---

# ✨ Features

## 🟢 Phase 1 – Crime Mapping & Visualization

- Interactive Karnataka crime map
- Live crime incident visualization
- PostgreSQL + PostGIS integration
- Synthetic crime data generation
- District-wise filtering
- REST APIs using FastAPI

---

## 🟡 Phase 2 – Hotspot Detection

- Crime Heatmaps
- Station-wise density visualization
- Red Zone Detection using Z-Score
- Day/Night crime filtering
- Weekday vs Weekend analysis

---

## 🔵 Phase 3 – Criminal Network Analysis

- Modus Operandi (MO) clustering
- Interactive criminal relationship graph
- Force-directed visualization
- Crime pattern discovery
- Cluster-based suspect analysis

---

## 🟣 Phase 4 – AI Risk Prediction

- XGBoost-based crime forecasting
- SHAP Explainability
- Station-wise risk scores
- Feature importance visualization
- Ground Truth Recovery Dashboard

---

## 🔴 Phase 5 – Officer Dashboard

- Station Officer View
- SCRB Analyst View
- Role-based dashboard UI
- Improved user experience
- Shared dashboard components

---

# 🏗️ System Architecture

```
                    React Frontend
                           │
          ┌────────────────┴────────────────┐
          │                                 │
      FastAPI Backend                 ML Services
          │                                 │
     PostgreSQL + PostGIS         XGBoost + SHAP
          │
   Synthetic Crime Generator
```

---

# 🛠️ Tech Stack

### Frontend
- React
- Vite
- Leaflet
- React Force Graph
- Recharts

### Backend
- Python
- FastAPI

### Database
- PostgreSQL
- PostGIS

### Machine Learning
- Scikit-learn
- XGBoost
- SHAP
- Pandas
- NumPy

---

# 📂 Project Structure

```
KSP-Crime-Intelligence/
│
├── backend/
├── frontend/
├── ml/
├── docs/
├── images/
├── requirements.txt
└── README.md
```

---

# 🚀 Installation

## Clone Repository

```bash
git clone <repository-url>
cd KSP-Crime-Intelligence
```

## Database Setup

```bash
createdb ksp_crime

psql -U postgres -d ksp_crime -f backend/schema.sql
```

## Backend

```bash
cd backend

python -m venv venv

source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt

python generate_data.py

uvicorn main:app --reload
```

## Frontend

```bash
cd frontend

npm install

npm run dev
```

Visit:

```
http://localhost:5173
```

---

# 📊 Future Enhancements

- Real-time CCTNS Integration
- Authentication & Authorization
- Live Crime Streaming
- AI-based Anomaly Detection
- Predictive Patrol Route Planning
- Cloud Deployment

---

# 👨‍💻 Author

**Keerthana K**

AI & Machine Learning Enthusiast | Full Stack Developer | ML Engineer Aspirant

---

⭐ If you found this project useful, consider giving it a star!
