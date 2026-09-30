const resultBox = document.getElementById("result");
const labelElement = document.getElementById("label");
const confidenceElement = document.getElementById("confidence");
const backendStatus = document.getElementById("backendStatus");

const API_URL = "http://127.0.0.1:8000/analyze";
const MAX_CHARS = 5000; // keeps huge pages from flooding the backend

function showResult(label, confidence, status) {
    labelElement.textContent = label;
    confidenceElement.textContent = confidence;
    backendStatus.textContent = status;
    resultBox.classList.remove("hidden");
}

async function getTextFromTab(mode) {
    const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true
    });

    const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        args: [mode],
        func: (mode) =>
            mode === "selected"
                ? window.getSelection().toString()
                : document.body.innerText
    });

    return results[0].result;
}

async function analyze(mode) {
    let text;

    // Step 1: read text from the page
    try {
        text = await getTextFromTab(mode);
    } catch (error) {
        console.error(error);
        showResult("-", "-", "Can't read this page ⚠️ (try a normal website)");
        return;
    }

    if (!text || text.trim().length === 0) {
        alert(
            mode === "selected"
                ? "Please select some text on the webpage first."
                : "This page has no readable text."
        );
        return;
    }

    text = text.trim().slice(0, MAX_CHARS);

    // Step 2: send it to the backend
    try {
        const response = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });

        if (!response.ok) {
            throw new Error("Backend request failed");
        }

        const data = await response.json();

        showResult(
            data.label,
            Math.round(data.confidence * 100) + "%",
            "Connected ✅"
        );
    } catch (error) {
        console.error(error);
        showResult("-", "-", "Connection failed ❌ (is uvicorn running?)");
    }
}

document.getElementById("analyzePage")
    .addEventListener("click", () => analyze("page"));

document.getElementById("checkSelectedText")
    .addEventListener("click", () => analyze("selected"));