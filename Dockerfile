FROM python:3.13-alpine

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY docker-entrypoint.sh .
COPY templates ./templates
COPY static ./static
COPY pyquestions ./pyquestions

EXPOSE 8000

CMD [ "sh", "docker-entrypoint.sh" ]
