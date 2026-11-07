from ultralytics import YOLO

model = YOLO("best (1).pt")
print(model.names)