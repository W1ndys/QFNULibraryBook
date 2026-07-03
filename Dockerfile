FROM python:3.12-slim

WORKDIR /app

COPY py/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY py/ .
COPY json/ /app/json/

ENTRYPOINT ["python"]
CMD ["get_seat_tomorrow_mode_1.py"]