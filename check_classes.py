from ultralytics import YOLO

model = YOLO("last.pt")
print(model.names)