document.getElementById("checkSelectedText").addEventListener("click", async () => {

    const resultBox = document.getElementById("result");
    const labelElement = document.getElementById("label");
    const confidenceElement = document.getElementById("confidence");
    const backendStatus = document.getElementById("backendStatus");

    try {

        const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true
        });

        const results = await chrome.scripting.executeScript({
            target: {
                tabId: tab.id
            },
            func: () => window.getSelection().toString()
        });

        const selectedText = results[0].result;

        if (!selectedText || selectedText.trim().length === 0) {
            alert("Please select some text on the webpage first.");
            return;
        }

        const response = await fetch(
            "http://127.0.0.1:8000/analyze",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    text: selectedText
                })
            }
        );

        if (!response.ok) {
            throw new Error("Backend request failed");
        }

        const data = await response.json();

        labelElement.textContent = data.label;

        confidenceElement.textContent =
            Math.round(data.confidence * 100) + "%";

        backendStatus.textContent = "Connected ✅";

        resultBox.classList.remove("hidden");

        console.log(
            "Selected text sent to TruthGuard:",
            selectedText
        );

    } catch (error) {

        console.error(error);

        backendStatus.textContent = "Connection failed ❌";

        resultBox.classList.remove("hidden");
    }
});