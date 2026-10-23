import { useState, useRef, useEffect, useCallback } from "react";
import { Camera, SwitchCamera, X, Loader2, Check } from "lucide-react";

// Live in-browser camera viewfinder. Captures one or more pages as image
// Files (video → canvas → toBlob) and hands them to onDone.
export default function CameraCapture({ isBrutal, onDone, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [facing, setFacing] = useState("user");
  const [pages, setPages] = useState([]);
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  // Acquire (or re-acquire on flip) the camera stream.
  useEffect(() => {
    let cancelled = false;
    const start = async () => {
      setStarting(true);
      setError(null);
      stopStream();
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: facing, width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
      } catch (e) {
        if (!cancelled) setError("We couldn't start your camera. Check that no other app is using it, then try again.");
      } finally {
        if (!cancelled) setStarting(false);
      }
    };
    start();
    return () => {
      cancelled = true;
    };
  }, [facing, stopStream]);

  // Always release the camera when the viewfinder unmounts.
  useEffect(() => stopStream, [stopStream]);

  const capturePage = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) return;
    const index = pages.length + 1;
    const file = new File([blob], `report-page-${index}.jpg`, { type: "image/jpeg" });
    setPages((prev) => [...prev, { file, url: URL.createObjectURL(blob) }]);
  };

  const removePage = (i) => {
    setPages((prev) => {
      URL.revokeObjectURL(prev[i].url);
      return prev.filter((_, idx) => idx !== i);
    });
  };

  const handleDone = () => {
    stopStream();
    onDone(pages.map((p) => p.file));
  };

  const handleCancel = () => {
    stopStream();
    pages.forEach((p) => URL.revokeObjectURL(p.url));
    onCancel();
  };

  const panelClass = isBrutal
    ? "bg-zinc-950 border border-zinc-800"
    : "bg-background/80 border border-border";

  return (
    <div className={`rounded-2xl p-3 space-y-3 ${panelClass}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold">
          {pages.length === 0 ? "Position the report in frame" : `${pages.length} page${pages.length > 1 ? "s" : ""} captured`}
        </span>
        <button type="button" onClick={handleCancel} className="text-muted-foreground hover:text-foreground" aria-label="Close camera">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="relative rounded-xl overflow-hidden bg-black aspect-[4/3]">
        <video ref={videoRef} playsInline muted autoPlay className="w-full h-full object-cover" />
        {starting && !error &&
          <div className="absolute inset-0 flex items-center justify-center text-white/80">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        }
        {error &&
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-white/90">
            {error}
          </div>
        }
        {!error &&
          <button
            type="button"
            onClick={() => setFacing((f) => (f === "user" ? "environment" : "user"))}
            className="absolute top-2 right-2 p-2 rounded-full bg-black/50 text-white hover:bg-black/70"
            aria-label="Flip camera">
            <SwitchCamera className="w-4 h-4" />
          </button>
        }
      </div>

      {pages.length > 0 &&
        <div className="flex gap-2 overflow-x-auto pb-1">
          {pages.map((p, i) =>
            <div key={p.url} className="relative shrink-0">
              <img src={p.url} alt={`Page ${i + 1}`} className="w-16 h-20 object-cover rounded-lg border border-border" />
              <button
                type="button"
                onClick={() => removePage(i)}
                className="absolute -top-1.5 -right-1.5 p-0.5 rounded-full bg-foreground text-background"
                aria-label={`Remove page ${i + 1}`}>
                <X className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
      }

      <button
        type="button"
        disabled={starting || !!error}
        onClick={capturePage}
        className={`w-full py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 ${
          isBrutal ? "bg-orange-600 hover:bg-orange-700 text-white" : "bg-primary hover:bg-primary/90 text-primary-foreground"
        }`}>
        <span className="flex items-center justify-center gap-2">
          <Camera className="w-5 h-5" />
          {pages.length === 0 ? "Capture page" : "Capture another page"}
        </span>
      </button>

      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={handleCancel}
          className="py-2.5 rounded-xl font-bold text-sm bg-muted text-muted-foreground hover:bg-border">
          Cancel
        </button>
        <button
          type="button"
          disabled={pages.length === 0}
          onClick={handleDone}
          className={`py-2.5 rounded-xl font-bold text-sm disabled:opacity-40 ${
            isBrutal ? "bg-orange-500 text-white" : "bg-primary text-primary-foreground"
          }`}>
          <span className="flex items-center justify-center gap-1.5">
            <Check className="w-4 h-4" /> Done
          </span>
        </button>
      </div>
    </div>
  );
}