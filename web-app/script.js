//Login functionality 
 document.addEventListener("DOMContentLoaded", function () {
      var loginBtn = document.getElementById("login-btn");
      var loginContainer = document.getElementById("login-container");
      var loginCloseBtn = document.getElementById("login-close-btn");
      var loginForm = document.getElementById("login-form");

      function openLoginContainer() {
        loginContainer.hidden = false;
      }

      function closeLoginContainer() {
        loginContainer.hidden = true;
      }

      loginBtn.addEventListener("click", openLoginContainer);
      loginCloseBtn.addEventListener("click", closeLoginContainer);

      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !loginContainer.hidden) {
          closeLoginContainer();
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

        closeLoginContainer();
    });
 });


//Audio recording functionality NEEDS WORK FOR AI
 document.addEventListener("DOMContentLoaded", function () {
      var startBtn = document.getElementById("start-btn");
      var stopBtn = document.getElementById("stop-btn");
      var statusEl = document.getElementById("status");
      var playback = document.getElementById("playback");

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

      function saveRecordingForHistory(blob) {
        var reader = new FileReader();
        reader.onload = function (e) {
          var dataUrl = e.target.result;

          var existing = localStorage.getItem("recordings");
          var recordings = existing ? JSON.parse(existing) : [];

          recordings.push({
            name: "Mic Recording " + (recordings.length + 1),
            dataUrl: dataUrl,
            addedAt: new Date().toISOString()
          });

          localStorage.setItem("recordings", JSON.stringify(recordings));
        };
        reader.readAsDataURL(blob);
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


    //History page functionality
     document.addEventListener("DOMContentLoaded", async function () {
      var historyList = document.getElementById("history-list");
      var emptyHistory = document.getElementById("empty-history");
      var errorMessage = document.getElementById("error-message");

      emptyHistory.hidden = true;
      errorMessage.hidden = true;

      try {
        const response = await fetch('/api/recordings');
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }

        const recordings = await response.json();

        if (!recordings || recordings.length === 0) {
          emptyHistory.hidden = false;
          return;
        }

        recordings.forEach(function (rec, index) {
          var li = document.createElement("li");

          var title = document.createElement("p");
          title.textContent = rec.name || ("Recording " + (index + 1));

          var date = document.createElement("p");
          var addedDate = rec.addedAt ? new Date(rec.addedAt) : new Date();
          date.textContent = "Added at: " + addedDate.toLocaleString();

          var audio = document.createElement("audio");
          audio.controls = true;
          audio.src = rec.audioUrl || rec.dataUrl || '';

          li.appendChild(title);
          li.appendChild(date);
          li.appendChild(audio);

          historyList.appendChild(li);
        });
      } catch (err) {
        console.error(err);
        errorMessage.textContent = "Could not load history from the server.";
        errorMessage.hidden = false;
        emptyHistory.hidden = false;
      }
    });