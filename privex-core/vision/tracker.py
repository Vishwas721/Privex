from enum import Enum
import math


class TrackState(Enum):
    TENTATIVE = 1
    ACTIVE = 2
    LOST = 3
    DELETED = 4


class TrackManager:
    def __init__(self):
        self.tracks = []
        self.next_id = 0
        self.MAX_AGE = 15     # Coast for 15 frames if OCR goes blind
        self.MIN_HITS = 1     # 🛑 FIX 1: Instant activation! No waiting for consecutive frames.
        self.MATCH_DIST = 400 # 🛑 FIX 2: Huge distance tolerance so YOLO boxes don't lose tracking on 4K screens.

    def _get_center(self, bbox):
        return ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)

    def update_tracks(self, new_bboxes):
        # 1. Predict (Age tracks)
        for track in self.tracks:
            track['time_since_update'] += 1
            if track['time_since_update'] > self.MAX_AGE:
                track['state'] = TrackState.DELETED
            elif track['state'] == TrackState.ACTIVE and track['time_since_update'] > 0:
                track['state'] = TrackState.LOST

        # 2. Match
        unmatched_bboxes = list(new_bboxes)
        for track in self.tracks:
            if track['state'] == TrackState.DELETED:
                continue

            best_match_idx = -1
            best_dist = float('inf')

            for i, bbox in enumerate(unmatched_bboxes):
                dist = math.hypot(
                    self._get_center(track['bbox'])[0] - self._get_center(bbox)[0],
                    self._get_center(track['bbox'])[1] - self._get_center(bbox)[1]
                )
                if dist < self.MATCH_DIST and dist < best_dist:
                    best_dist = dist
                    best_match_idx = i

            if best_match_idx != -1:
                track['bbox'] = unmatched_bboxes.pop(best_match_idx)
                track['hits'] += 1
                track['time_since_update'] = 0

                if track['state'] == TrackState.TENTATIVE and track['hits'] >= self.MIN_HITS:
                    track['state'] = TrackState.ACTIVE
                elif track['state'] == TrackState.LOST:
                    track['state'] = TrackState.ACTIVE

        # 3. Spawn (Instantly active if MIN_HITS is 1)
        for bbox in unmatched_bboxes:
            self.tracks.append({
                'id': self.next_id,
                'bbox': bbox,
                'state': TrackState.ACTIVE if self.MIN_HITS <= 1 else TrackState.TENTATIVE,
                'hits': 1,
                'time_since_update': 0
            })
            self.next_id += 1

        self.tracks = [t for t in self.tracks if t['state'] != TrackState.DELETED]
        valid_boxes = [t['bbox'] for t in self.tracks if t['state'] in (TrackState.ACTIVE, TrackState.LOST)]
        return valid_boxes