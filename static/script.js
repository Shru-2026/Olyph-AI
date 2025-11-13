document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Olyph AI script loaded successfully");

  const chatBody = document.getElementById("chat-body");
  const buttons = document.querySelectorAll(".chat-btn");
  const buttonContainer = document.querySelector(".button-container");
  const homeButton = document.getElementById("homeBtn");
  const sendBtn = document.getElementById("sendBtn");
  const userInput = document.getElementById("userInput");

  let optionSelected = false;
  let selectedMode = null;

  function addMessage(content, sender = "bot") {
    const message = document.createElement("div");
    message.classList.add(sender === "bot" ? "bot-message" : "user-message");
    message.textContent = content;
    chatBody.appendChild(message);
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function sanityCheck(option) {
    const validOptions = ["ask", "survey", "report"];
    return validOptions.includes(option);
  }

  function handleSelection(option) {
    if (optionSelected) return;
    if (!sanityCheck(option)) return addMessage("⚠️ Invalid option selected!", "bot");

    optionSelected = true;
    selectedMode = option;

    // Hide the buttons
    buttonContainer.style.display = "none";

    // Show the Home button
    homeButton.style.display = "inline-block";

    if (option === "ask") {
      addMessage("Thank you for choosing Ask me anything. Connecting you with Olyph AI...", "bot");
      setTimeout(() => {
        addMessage("💬 Olyph AI is online! You can now ask about Olyphaunt Solutions or healthcare.", "bot");
      }, 1000);
    } else if (option === "survey") {
      addMessage("Thank you for choosing Survey Agent! Opening the form now...", "bot");
      setTimeout(() => {
        window.open("https://forms.gle/u4pRVf1bAWSbWJA7A", "_blank");
      }, 1000);
    } else if (option === "report") {
      addMessage("Thank you for choosing Report Agent. Connecting to reporting assistant...", "bot");
    }
  }

  async function callConversationalAgent(userMessage) {
    addMessage(userMessage, "user");

    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });

      const data = await response.json();
      addMessage(data.reply, "bot");
    } catch (error) {
      addMessage("⚠️ Could not connect to Olyph AI server.", "bot");
      console.error(error);
    }
  }

  async function handleSend() {
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = "";

    if (selectedMode === "ask") {
      await callConversationalAgent(message);
    } else {
      addMessage(message, "user");
      setTimeout(() => addMessage("We’ll get back to you soon.", "bot"), 500);
    }
  }

  // 🟢 Send button click
  sendBtn.addEventListener("click", handleSend);

  // 🟢 Enter key press to send message
  userInput.addEventListener("keypress", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault(); // Prevent newline
      handleSend();
    }
  });

  // 🟢 Button click events
  document.getElementById("askBtn").addEventListener("click", () => handleSelection("ask"));
  document.getElementById("surveyBtn").addEventListener("click", () => handleSelection("survey"));
  document.getElementById("reportBtn").addEventListener("click", () => handleSelection("report"));

  // 🏠 Home Button click event
  homeButton.addEventListener("click", () => {
    resetChat();
  });

  function resetChat() {
    chatBody.innerHTML = "";
    addMessage("👋 Greetings, this is OlyphAI. How can I help you?");
    buttonContainer.style.display = "flex";
    homeButton.style.display = "none";
    optionSelected = false;
    selectedMode = null;
  }
});
