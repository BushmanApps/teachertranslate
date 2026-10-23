import { useState, useRef, useEffect } from "react";
import { Upload, FileText, X, Loader2, Camera } from "lucide-react";
import { base44 } from "@/api/base44Client";
import { useCameraPermission } from "@/hooks/useCameraPermission";
import { rePushSentinel } from "@/lib/safeWebApi";
import CameraCapture from "@/components/CameraCapture";

// The `capture` attribute is only honoured by mobile browsers — on desktop it
// is ignored and the input opens a plain file picker, so we use the live
// in-browser viewfinder there instead.
const supportsNativeCapture = () =>
  typeof document !== "undefined" &&
  "capture" in document.createElement("input") &&
  typeof window !== "undefined" &&
  window.matchMedia?.("(pointer: coarse)").matches;

export default function UploadSection({ onTextReady, isBrutal, disabled, onBlocked }) {
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState(null);
  const [extractedText, setExtractedText] = useState(null);
  const [extractError, setExtractError] = useState(null);
  const [manualText, setManualText] = useState("");
  const [showManual, setShowManual] = useState(false);
  const fileRef = useRef(null);
  const cameraRef = useRef(null);
  const manualRef = useRef(null);
  const { permission: cameraPermission, request: requestCamera } = useCameraPermission();
  const cameraGranted = cameraPermission === "granted";
  // Locally confirmed the camera works — set the moment a camera capture
  // succeeds. The native <input capture> path bypasses getUserMedia, so the
  // Permissions-API hook may never learn it was granted; this flag makes the
  // button reflect "usable" instantly after the first successful photo.
  const [cameraConfirmed, setCameraConfirmed] = useState(false);
  const cameraReady = cameraGranted || cameraConfirmed;
  const [deniedNotice, setDeniedNotice] = useState(false);
  const [showCamera, setShowCamera] = useState(false);

  // Show the denied notice automatically when camera permission is denied
  // (e.g. after the user dismisses the native browser prompt), and reset
  // it as soon as permission is granted again.
  useEffect(() => {
    if (cameraReady) {
      setDeniedNotice(false);
    } else if (cameraPermission === "denied") {
      setDeniedNotice(true);
    }
  }, [cameraReady, cameraPermission]);

  // When the user opens manual text entry, slide the card to the top of the
  // screen (past the header) so the text field and Translate button stay
  // fully visible above the phone keyboard.
  useEffect(() => {
    if (showManual && manualRef.current) {
      // Scroll the manual entry card to the very top of the viewport so the
      // textarea and Translate button stay visible above the native keyboard
      // (which the app WebView doesn't account for in the viewport height).
      // Use instant (non-smooth) scroll + a delayed re-scroll because the
      // smooth scroll can be interrupted by the keyboard appearing.
      const scrollTop = () => {
        window.scrollTo({ top: 0, behavior: "auto" });
      };
      scrollTop();
      // Re-scroll at multiple intervals because the native app keyboard
      // overlay appears asynchronously and isn't accounted for in the
      // viewport height — multiple retries ensure the card reaches the top.
      const timers = [100, 300, 600, 1000].map((ms) => setTimeout(scrollTop, ms));
      return () => timers.forEach(clearTimeout);
    }
  }, [showManual]);

  const handleFile = async (file, method = "file") => {
    if (!file) return;
    // A camera capture succeeded → the camera is usable. Flag it so the
    // button updates to its usable state instantly.
    if (method === "camera") setCameraConfirmed(true);
    setFileName(file.name);
    setExtractedText(null);
    setExtractError(null);
    setUploading(true);
    try {
      const { file_url } = await base44.integrations.Core.UploadFile({ file });
      const res = await base44.functions.invoke("extractTextFromFile", { fileUrl: file_url });
      const text = res.data?.text;
      if (text && text.trim()) {
        setExtractedText(text);
      } else {
        setExtractError("We couldn't read any text from that file. If it has redactions (blacked-out areas), try removing them or paste the text manually below.");
      }
    } catch (e) {
      console.error(e);
      setExtractError("That file took too long to read or couldn't be processed. Redacted or image-heavy PDFs can cause this — try pasting the report text manually instead.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
      if (cameraRef.current) cameraRef.current.value = "";
      // The native file/camera Intent consumed the global back-button
      // sentinel history entry while the picker was open. Re-push it so
      // the hardware back button keeps reaching the app after return.
      rePushSentinel();
    }
  };

  // Multi-page camera capture: upload + read each page, then join the text
  // in page order so the rest of the flow behaves like a single report.
  const handleCapturedPages = async (files) => {
    setShowCamera(false);
    if (!files?.length) return;
    setCameraConfirmed(true);
    setFileName(files.length === 1 ? files[0].name : `${files.length} scanned pages`);
    setExtractedText(null);
    setExtractError(null);
    setUploading(true);
    try {
      const parts = [];
      for (const file of files) {
        const { file_url } = await base44.integrations.Core.UploadFile({ file });
        const res = await base44.functions.invoke("extractTextFromFile", { fileUrl: file_url });
        const text = res.data?.text;
        if (text && text.trim()) parts.push(text.trim());
      }
      if (parts.length) {
        setExtractedText(parts.join("\n\n"));
      } else {
        setExtractError("We couldn't read any text from those photos. Try again with better lighting and the page filling the frame, or paste the text manually below.");
      }
    } catch (e) {
      console.error(e);
      setExtractError("Those photos couldn't be processed. Try again, or paste the report text manually instead.");
    } finally {
      setUploading(false);
    }
  };

  // If the user cancels the native file/camera picker without choosing a
  // file, the input change event still fires (with no file) — re-push the
  // sentinel so the back button keeps working. Also handles the blur
  // fallback on iOS where the cancel event fires as a blur.
  const handleInputChange = (e, method) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file, method);
    } else {
      rePushSentinel();
    }
  };

  const handleClear = () => {
    setFileName(null);
    setExtractedText(null);
    setExtractError(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleTranslate = () => {
    if (extractedText) {
      base44.analytics.track({ eventName: "report_uploaded", properties: { method: "file" } });
      onTextReady(extractedText);
    }
  };

  const handleManualSubmit = () => {
    if (manualText.trim()) {
      base44.analytics.track({ eventName: "report_uploaded", properties: { method: "manual_text" } });
      onTextReady(manualText.trim());
    }
  };

  // On every press, re-verify camera permission. Only open the camera when
  // access is granted; if it isn't, prompt again and keep the button disabled.
  const handleCameraClick = async () => {
    if (disabled) { onBlocked?.(); return; }
    if (uploading) return;
    setDeniedNotice(false);
    // Desktop (no native capture support) → live in-browser viewfinder.
    const openCamera = () => {
      if (supportsNativeCapture()) {
        cameraRef.current?.click();
      } else {
        setShowCamera(true);
      }
    };
    if (cameraReady) {
      openCamera();
    } else if (cameraPermission === "denied") {
      // Previously denied — show in-app notice (browser won't re-prompt)
      setDeniedNotice(true);
    } else {
      // "prompt" or "unknown" — request permission (triggers native prompt)
      const granted = await requestCamera();
      if (granted) {
        openCamera();
      } else {
        setDeniedNotice(true);
      }
    }
  };

  const btnClass = `flex flex-col items-center gap-1.5 p-3 sm:p-5 rounded-2xl transition-all font-bold text-sm disabled:opacity-50 ${
  isBrutal ?
  "border-2 border-dashed border-orange-600 text-orange-400 hover:bg-orange-950/30" :
  "bg-[#d4ede5] text-foreground hover:bg-[#c4e0d8]"}`;


  return (
    <div className="space-y-3">
      {showCamera &&
        <CameraCapture
          isBrutal={isBrutal}
          onDone={handleCapturedPages}
          onCancel={() => setShowCamera(false)} />
      }
      {!showManual ?
      <>
          <div className={`grid grid-cols-2 gap-2 sm:gap-6 ${showCamera ? "hidden" : ""}`}>
            {/* Upload button — file picker only, never triggers the camera.
              Uses a real <button> + programmatic input.click() because
              <label>-wrapped hidden inputs don't forward taps in native
              WebView (iOS/Android app). */}
            <button
            type="button"
            disabled={uploading}
            onClick={() => { if (disabled) { onBlocked?.(); return; } fileRef.current?.click(); }}
            className={`${btnClass} cursor-pointer ${uploading ? "opacity-50" : ""}`}>
            
              <Upload className="w-6 h-6 sm:w-8 sm:h-8" />
              <span>Upload File</span>
              <span className="text-xs font-normal text-muted-foreground">PDF or image</span>
            </button>
            <input
            ref={fileRef}
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp,image/heic"
            className="hidden"
            onChange={(e) => handleInputChange(e, "file")} />

            {/* Camera button — capture="environment" opens the native camera */}
            <button
            type="button"
            disabled={uploading}
            onClick={handleCameraClick}
            className={`${btnClass} ${uploading ? "opacity-50" : ""} ${!cameraReady ? "opacity-60 grayscale cursor-not-allowed" : "cursor-pointer"}`}>

              <Camera className="w-6 h-6 sm:w-8 sm:h-8" />
              <span>Scan with Camera</span>
              <span className="text-xs font-normal text-muted-foreground">{cameraReady ? "Take a photo" : "Camera permission needed — tap to allow"}</span>
            </button>
            <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => handleInputChange(e, "camera")} />
          
          </div>

          {deniedNotice &&
        <div className={`rounded-xl p-3 text-sm space-y-1 ${isBrutal ? "bg-orange-950/40 border border-orange-800 text-orange-300" : "bg-amber-50 border border-amber-200 text-amber-800"}`}>
              <p className="font-bold">Camera access is blocked</p>
              <p className="text-xs">
                We can't re-ask automatically once you've denied camera permission. Enable camera for this app in your browser or device settings, then press the button again.
              </p>
              <button onClick={() => setDeniedNotice(false)} className="text-xs font-bold underline underline-offset-2 mt-1">
                Dismiss
              </button>
            </div>
        }

          <button
          onClick={() => { if (disabled) { onBlocked?.(); return; } setShowManual(true); }}
          className={`w-full text-center text-muted-foreground hover:text-foreground underline underline-offset-2 text-base sm:w-1/2 sm:mx-auto sm:block sm:rounded-2xl sm:p-5 sm:no-underline sm:border-2 sm:border-dashed sm:font-bold sm:transition-all ${
          isBrutal ?
          "sm:border-orange-600 sm:text-orange-400 sm:hover:bg-orange-950/30" :
          "sm:border-[#8cc4b0] sm:text-foreground sm:hover:bg-[#d4ede5]"}`}>

            Or paste / type report text manually
          </button>

          {/* Uploading state */}
          {uploading &&
        <div className={`flex items-center justify-center gap-2 py-2 text-sm font-semibold ${isBrutal ? "text-orange-400" : "text-primary"}`}>
              <Loader2 className="w-4 h-4 animate-spin" />
              Reading your child's report...
            </div>
        }

          {/* File ready — show Translate button */}
          {fileName && !uploading &&
        <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted rounded-lg px-3 py-2">
                <FileText className="w-4 h-4 shrink-0" />
                <span className="truncate flex-1">{fileName}</span>
                <button onClick={handleClear} className="shrink-0">
                  <X className="w-4 h-4" />
                </button>
              </div>
              {extractError &&
          <div className={`rounded-xl p-3 text-sm space-y-2 ${isBrutal ? "bg-orange-950/40 border border-orange-800 text-orange-300" : "bg-red-50 border border-red-100 text-red-700"}`}>
                  <p>{extractError}</p>
                  <button
              onClick={() => {handleClear();setShowManual(true);}}
              className="font-bold underline underline-offset-2">
              
                    Paste text manually →
                  </button>
                </div>
          }
              {extractedText &&
          <button
            disabled={disabled}
            onClick={handleTranslate}
            className={`w-full py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 ${
            isBrutal ?
            "bg-orange-600 hover:bg-orange-700 text-white" :
            "bg-primary hover:bg-primary/90 text-primary-foreground"}`
            }>
            
                  <span className="flex items-center justify-center gap-2">
                    <img src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png" alt="" className="w-7 h-7 object-contain" />
                    {isBrutal ? "💥 Translate this!" : "Translate this!"}
                  </span>
                </button>
          }
            </div>
        }
        </> :

      <div ref={manualRef} className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold">Paste or type report comment text</span>
            <button onClick={() => setShowManual(false)} className="text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
          </div>
          <textarea
          value={manualText}
          onChange={(e) => setManualText(e.target.value)}
          onFocus={() => { setTimeout(() => window.scrollTo({ top: 0, behavior: "auto" }), 100); }}
          placeholder="Paste or type the teacher's comments here..."
          rows={6}
          className={`w-full rounded-xl border border-input bg-background p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring ${isBrutal ? "placeholder:text-zinc-400 text-zinc-200" : ""}`} />
        
          <button
          disabled={!manualText.trim() || disabled}
          onClick={handleManualSubmit}
          className={`w-full py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-40 ${
          isBrutal ?
          "bg-orange-600 hover:bg-orange-700 text-white" :
          "bg-primary hover:bg-primary/90 text-primary-foreground"}`
          }>
          
            <span className="flex items-center justify-center gap-2">
              <img src="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets/images/public/69fc81cf4f6a0ae5ab617e2b/c7bffff4e_TTLogo01.png" alt="" className="w-7 h-7 object-contain" />
              {isBrutal ? "💥 Translate this!" : "Translate this!"}
            </span>
          </button>
        </div>
      }

    </div>);

}