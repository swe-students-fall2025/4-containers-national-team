// Login / Signup functionality 
document.addEventListener("DOMContentLoaded", function () {
  var loginBtn = document.getElementById("login-btn");
  var loginContainer = document.getElementById("login-container");
  var loginCloseBtn = document.getElementById("login-close-btn");
  var loginForm = document.getElementById("login-form");
  var signupBtn = document.getElementById("signup-btn");
  var signupContainer = document.getElementById("signup-container");
  var signupCloseBtn = document.getElementById("signup-close-btn");
  var signupForm = document.getElementById("signup-form");
  var logoutBtn = document.getElementById("logout-btn");     

  if (logoutBtn) {                                           
    logoutBtn.addEventListener("click", async function () {  
      await fetch("/api/logout", {                           
        method: "POST",                                      
        headers: {"Content-Type": "application/json"}        
      });                                                    
      window.location.href = "/";                            
    });                                                      
  }



  // If we're not on a page with the login UI, do nothing
  if (!loginBtn || !loginContainer || !loginCloseBtn || !loginForm) {
    return;
  }

  function openLoginContainer() {
    loginContainer.hidden = false;
  }

  function closeLoginContainer() {
    loginContainer.hidden = true;
  }

  function openSignupContainer() {
    signupContainer.hidden = false;
  }

  function closeSignupContainer() {
    signupContainer.hidden = true;
  }


  loginBtn.addEventListener("click", openLoginContainer);
  loginCloseBtn.addEventListener("click", closeLoginContainer);
  signupBtn.addEventListener("click", openSignupContainer);
  signupCloseBtn.addEventListener("click", closeSignupContainer);


  document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") {      
    if (!loginContainer.hidden){
       closeLoginContainer();     
    }
    if (!signupContainer.hidden) {
      closeSignupContainer();
    }
  }
});


  loginForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    var username = document.getElementById("login-username").value;
    var password = document.getElementById("login-password").value;

    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await response.json();
    if (!response.ok) {                   
      alert(data.message || "Login failed");   
      return;                             
    }
    window.location.href = "/pitch";                
  });
  signupForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    var username = document.getElementById("signup-username").value;
    var password = document.getElementById("signup-password").value;

    const response = await fetch('/api/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });

    const data = await response.json();   
    if (!response.ok) {                   
      alert(data.message || "Login failed");
      return;
    }
    closeSignupContainer();
    openLoginContainer();
           
});

});



// Audio recording functionality
document.addEventListener("DOMContentLoaded", function () {
  var startBtn = document.getElementById("start-btn");
  var stopBtn = document.getElementById("stop-btn");
  var statusEl = document.getElementById("status");
  var playback = document.getElementById("playback");
  var analysisEl = document.getElementById("analysis-result");

  // If we're not on the Record page, do nothing
  if (!startBtn || !stopBtn || !statusEl || !playback) {
    return;
  }

  var mediaRecorder = null;
  var chunks = [];

  async function initMedia() {
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = function (e) {
        chunks.push(e.data);
      };

      mediaRecorder.onstop = function () {
        var blob = new Blob(chunks, { type: "audio/webm" });
        chunks = [];

        var url = URL.createObjectURL(blob);
        playback.src = url;

        statusEl.textContent = "Recording finished.";

        // Upload to backend and show analysis
        saveRecordingForHistory(blob);
      };

      statusEl.textContent = "Microphone ready. Press 'Start Recording'.";
      startBtn.disabled = false;
    } catch (err) {
      console.error(err);
      statusEl.textContent = "Microphone access denied or unavailable.";
      startBtn.disabled = true;
    }
  }

  // Now uploads to /api/upload instead of localStorage
  async function saveRecordingForHistory(blob) {
    try {
      var formData = new FormData();
      formData.append("audio", blob, "recording.webm");

      var response = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      var data = await response.json();
      statusEl.textContent = "Recording uploaded successfully.";

      if (analysisEl && data.analysis) {
        var a = data.analysis;
        var pitchHz = a.pitch_hz;
        var pitchNote = a.pitch_note;
        var confidence = a.confidence;

        var text = "Detected pitch: ";
        if (pitchNote) {
          text += pitchNote;
          if (pitchHz != null) {
            text += " (" + pitchHz.toFixed ? pitchHz.toFixed(1) + " Hz" : pitchHz + " Hz" + ")";
          }
        } else if (pitchHz != null) {
          text += (pitchHz.toFixed ? pitchHz.toFixed(1) : pitchHz) + " Hz";
        } else {
          text += "(not available)";
        }

        if (confidence != null) {
          text += " (confidence " + Math.round(confidence * 100) + "%)";
        }

        analysisEl.textContent = text;
      }
    } catch (err) {
      console.error(err);
      statusEl.textContent = "Error uploading recording.";
      if (analysisEl) {
        analysisEl.textContent = "";
      }
    }
  }

  startBtn.addEventListener("click", function () {
    if (!mediaRecorder) {
      statusEl.textContent = "Microphone not initialized yet.";
      return;
    }
    chunks = [];
    mediaRecorder.start();
    statusEl.textContent = "Recording... speak now.";
    startBtn.disabled = true;
    stopBtn.disabled = false;

    if (analysisEl) {
      analysisEl.textContent = "";
    }
  });

  stopBtn.addEventListener("click", function () {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      statusEl.textContent = "Stopping recording...";
      startBtn.disabled = false;
      stopBtn.disabled = true;
    }
  });

  initMedia();
});


// History page functionality
document.addEventListener("DOMContentLoaded", async function () {
  var historyList = document.getElementById("history-list");
  var emptyHistory = document.getElementById("empty-history");
  var errorMessage = document.getElementById("error-message");

  // If we're not on the History page, do nothing
  if (!historyList) {
    return;
  }

  if (emptyHistory) emptyHistory.hidden = true;
  if (errorMessage) errorMessage.hidden = true;

  try {
    const response = await fetch('/api/recordings');
    if (!response.ok) {
      throw new Error('Network response was not ok');
    }

    const data = await response.json();
    const recordings = data.recordings || [];

    if (!recordings || recordings.length === 0) {
      if (emptyHistory) emptyHistory.hidden = false;
      return;
    }

    recordings.forEach(function (rec, index) {
      var li = document.createElement("li");

      var title = document.createElement("p");
      var analysis = rec.analysis || {};
      var pitchHz = analysis.pitch_hz;
      var pitchNote = analysis.pitch_note;
      var confidence = analysis.confidence;

      var titleText = "Recording " + (index + 1) + " - ";
      if (pitchNote && pitchHz != null) {
        titleText += pitchNote + " (" + (pitchHz.toFixed ? pitchHz.toFixed(1) : pitchHz) + " Hz)";
      } else if (pitchHz != null) {
        titleText += (pitchHz.toFixed ? pitchHz.toFixed(1) : pitchHz) + " Hz";
      } else {
        titleText += "Pitch not available";
      }
      if (confidence != null) {
        titleText += " (confidence " + Math.round(confidence * 100) + "%)";
      }
      title.textContent = titleText;

      var date = document.createElement("p");
      var createdDate = rec.created_at ? new Date(rec.created_at) : new Date();
      date.textContent = "Recorded at: " + createdDate.toLocaleString();

      var audio = document.createElement("audio");
      audio.controls = true;
      audio.src = rec.audio_url || '';

      li.appendChild(title);
      li.appendChild(date);
      li.appendChild(audio);

      historyList.appendChild(li);
    });
  } catch (err) {
    console.error(err);
    if (errorMessage) {
      errorMessage.textContent = "Could not load history from the server.";
      errorMessage.hidden = false;
    }
    if (emptyHistory) emptyHistory.hidden = false;
  }
});
