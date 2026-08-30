from fastapi import FastAPI

app = FastAPI(title="Embeddable Widget Platform")

@app.get("/health")
def health_check():
    return {"status" : "ok"}