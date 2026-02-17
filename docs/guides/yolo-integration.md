# YOLO11 Integration Guide for TYVYX Drone

This guide shows how to integrate YOLO11 object detection with your TYVYX WiFi drone using OpenCV.

## Quick Start

### 1. Install YOLO11

```bash
pip install ultralytics
```

### 2. Download YOLO11 Model

```bash
# Download a pre-trained model (nano is fastest for real-time)
# This will auto-download on first use
python -c "from ultralytics import YOLO; model = YOLO('yolo11n.pt')"
```

Available models (size vs speed tradeoff):
- `yolo11n.pt` - Nano (fastest, least accurate)
- `yolo11s.pt` - Small
- `yolo11m.pt` - Medium
- `yolo11l.pt` - Large
- `yolo11x.pt` - Extra Large (slowest, most accurate)

### 3. Enable YOLO in Code

Open `drone_controller_yolo.py` and uncomment the YOLO code in the `DroneVideoProcessor` class:

**In `load_yolo_model()` method (line ~30):**
```python
def load_yolo_model(self, model_path: str = "yolo11n.pt"):
    try:
        from ultralytics import YOLO  # Uncomment this
        self.yolo_model = YOLO(model_path)  # Uncomment this
        self.yolo_enabled = True  # Uncomment this
        print(f"YOLO11 model loaded: {model_path}")  # Uncomment this
        return True  # Uncomment this
```

**In `process_frame()` method (line ~70):**
```python
if self.yolo_enabled and self.yolo_model is not None:
    # Uncomment all this block:
    results = self.yolo_model(frame, verbose=False)
    
    for result in results:
        boxes = result.boxes
        for box in boxes:
            # Get box coordinates
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = result.names[class_id]
            
            # Store detection
            detections.append({
                'class': class_name,
                'confidence': confidence,
                'bbox': (int(x1), int(y1), int(x2), int(y2))
            })
            
            # Draw on frame
            cv2.rectangle(processed_frame, (int(x1), int(y1)), 
                         (int(x2), int(y2)), (0, 255, 0), 2)
            
            # Draw label
            label = f"{class_name} {confidence:.2f}"
            cv2.putText(processed_frame, label, 
                       (int(x1), int(y1) - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (0, 255, 0), 2)
```

### 4. Run

```bash
python drone_controller_yolo.py
```

Press `Y` to load the YOLO model when the video stream starts.

## Usage Examples

### Basic Object Detection

```python
from drone_controller_yolo import TYVYXDroneYOLO
import cv2

# Create and connect
drone = TYVYXDroneYOLO()
drone.connect()
drone.start_video_stream()

# Load YOLO
drone.video_processor.load_yolo_model("yolo11n.pt")

# Process frames
while True:
    ret, frame = drone.get_frame()
    if ret:
        processed_frame, detections = drone.video_processor.process_frame(frame)
        
        # Print detections
        for det in detections:
            print(f"Detected {det['class']} with {det['confidence']:.2f} confidence")
        
        cv2.imshow('Drone', processed_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

drone.disconnect()
cv2.destroyAllWindows()
```

### Track Specific Objects

```python
# Track only people
target_classes = ['person']

while True:
    ret, frame = drone.get_frame()
    if ret:
        processed_frame, detections = drone.video_processor.process_frame(frame)
        
        # Filter for target classes
        people = [d for d in detections if d['class'] in target_classes]
        
        if people:
            print(f"Found {len(people)} person(s)")
            # Could trigger drone actions here
        
        cv2.imshow('Drone', processed_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
```

### Count Objects

```python
from collections import Counter

object_counts = Counter()

while True:
    ret, frame = drone.get_frame()
    if ret:
        processed_frame, detections = drone.video_processor.process_frame(frame)
        
        # Count objects
        for det in detections:
            object_counts[det['class']] += 1
        
        # Display counts every 100 frames
        if frame_count % 100 == 0:
            print("Object counts:", dict(object_counts))
        
        cv2.imshow('Drone', processed_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
```

### Save Detections to File

```python
import json
from datetime import datetime

detection_log = []

while True:
    ret, frame = drone.get_frame()
    if ret:
        processed_frame, detections = drone.video_processor.process_frame(frame)
        
        # Log detections with timestamp
        if detections:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'detections': detections
            }
            detection_log.append(log_entry)
        
        cv2.imshow('Drone', processed_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# Save log
with open('detection_log.json', 'w') as f:
    json.dump(detection_log, f, indent=2)
```

## Advanced Features

### Custom YOLO Model

Train your own YOLO11 model for specific objects:

```python
from ultralytics import YOLO

# Train custom model
model = YOLO('yolo11n.pt')
model.train(data='custom_dataset.yaml', epochs=100)

# Use in drone controller
drone.video_processor.load_yolo_model('runs/detect/train/weights/best.pt')
```

### Adjust Detection Confidence

```python
class DroneVideoProcessor:
    def __init__(self):
        self.confidence_threshold = 0.5  # Add this
        # ... rest of __init__
    
    def process_frame(self, frame):
        if self.yolo_enabled and self.yolo_model is not None:
            # Add confidence parameter
            results = self.yolo_model(frame, conf=self.confidence_threshold, verbose=False)
            # ... rest of processing
```

### Optimize for Performance

```python
# Use smaller input size for faster processing
results = self.yolo_model(frame, imgsz=416, verbose=False)  # Default is 640

# Process every Nth frame
if frame_count % 3 == 0:  # Process every 3rd frame
    results = self.yolo_model(frame, verbose=False)
```

### Object Tracking

```python
# Enable tracking across frames
results = self.yolo_model.track(frame, persist=True, verbose=False)

# Access track IDs
for result in results:
    boxes = result.boxes
    if boxes.id is not None:
        track_ids = boxes.id.cpu().numpy()
        # Use track_ids for persistent tracking
```

## Performance Tips

### For Real-Time Detection:

1. **Use smaller model**: Start with `yolo11n.pt`
2. **Reduce resolution**: Process at 640x480 or lower
3. **Skip frames**: Process every 2-3 frames
4. **Lower confidence**: Use higher threshold (0.6-0.8)
5. **Limit classes**: Filter for specific objects only

```python
# Optimized settings
drone.video_processor.load_yolo_model("yolo11n.pt")  # Nano model
results = model(frame, 
                imgsz=416,           # Smaller size
                conf=0.6,            # Higher threshold
                classes=[0, 1, 2])   # Only person, bicycle, car
```

### Hardware Acceleration:

```python
# Use GPU if available
from ultralytics import YOLO

model = YOLO('yolo11n.pt')
model.to('cuda')  # Or 'mps' for Mac

# Check device
print(f"Using device: {model.device}")
```

## YOLO11 Classes

YOLO11 detects 80 common objects:

```python
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
    'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
    'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier',
    'toothbrush'
]
```

## Troubleshooting

### "No module named 'ultralytics'"
```bash
pip install ultralytics
```

### Slow FPS
- Use smaller model (yolo11n.pt)
- Reduce input size: `imgsz=416`
- Process fewer frames: Skip every other frame
- Use GPU if available

### "CUDA out of memory"
```python
# Use CPU instead
model.to('cpu')

# Or use smaller batch size
results = model(frame, imgsz=416)
```

### Detection Quality Issues
- Increase model size (yolo11s.pt or yolo11m.pt)
- Lower confidence threshold
- Ensure good lighting in video feed
- Check camera focus

## Example Use Cases

### 1. People Counting
Track number of people in drone view

### 2. Object Following
Detect and follow a specific object

### 3. Search and Rescue
Find people in large areas

### 4. Wildlife Monitoring
Detect and count animals

### 5. Traffic Monitoring
Count vehicles and analyze patterns

### 6. Security Surveillance
Detect intruders or suspicious activity

## Next Steps

1. Install ultralytics: `pip install ultralytics`
2. Run `python drone_controller_yolo.py`
3. Press `Y` to load YOLO model
4. Start detecting objects!

For more YOLO11 documentation: https://docs.ultralytics.com/
