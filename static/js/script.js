document.addEventListener('DOMContentLoaded', () => {
    const inputField = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const chatWindow = document.getElementById('chat-window');
    const clock = document.getElementById('clock');
    const cpuLoad = document.getElementById('cpu-load');
    const memLoad = document.getElementById('mem-load');

    // --- Clock & Sys Stats ---
    function updateTime() {
        const now = new Date();
        clock.innerText = now.toLocaleTimeString('en-US', { hour12: false });
    }
    setInterval(updateTime, 1000);
    updateTime();

    setInterval(() => {
        cpuLoad.innerText = Math.floor(Math.random() * 30) + 10;
        memLoad.innerText = Math.floor(Math.random() * 20) + 30;
    }, 3000);

    // --- Chat Logic ---
    function addMessage(text, sender, sources = []) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', sender === 'user' ? 'user-msg' : 'bot-msg');

        const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });

        let header = sender === 'user' ? '[USER]' : '[SYSTEM]';
        let htmlContent = `<span class="timestamp">${header} ${timestamp}</span><div class="content"></div>`;

        msgDiv.innerHTML = htmlContent;
        chatWindow.appendChild(msgDiv);

        const contentDiv = msgDiv.querySelector('.content');

        if (sender === 'user') {
            contentDiv.innerText = text;
            scrollToBottom();
        } else {
            typeWriter(contentDiv, text, sources);
        }
    }

    function typeWriter(element, text, sources) {
        let i = 0;
        const speed = 10; // Typing speed in ms

        // Simple Markdown parsing for bold and code
        // Note: For a robust app, use a library like marked.js
        // Here we just render text as is for the typewriter effect, 
        // usually dealing with HTML in typewriter is tricky.
        // For simplicity, we'll treat text as plain text or pre-formatted HTML.
        // Or we can just insert the whole innerHTML if we don't need real-time typing of HTML tags.

        // Let's do a simple character rendering
        function type() {
            if (i < text.length) {
                element.innerHTML += text.charAt(i) === '\n' ? '<br>' : text.charAt(i);
                i++;
                scrollToBottom();
                setTimeout(type, speed);
            } else {
                // Done typing, add sources
                if (sources && sources.length > 0) {
                    const sourceContainer = document.createElement('div');
                    sourceContainer.style.marginTop = '10px';
                    sources.forEach(src => {
                        const span = document.createElement('span');
                        span.classList.add('source-tag');
                        span.innerText = `SRC: ${src.metadata.source.split('\\').pop()}`; // Show only filename
                        sourceContainer.appendChild(span);
                    });
                    element.appendChild(sourceContainer);
                    scrollToBottom();
                }
            }
        }
        type();
    }

    function scrollToBottom() {
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    async function sendMessage() {
        const text = inputField.value.trim();
        if (!text) return;

        addMessage(text, 'user');
        inputField.value = '';
        inputField.disabled = true;

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await response.json();

            if (data.error) {
                addMessage(`ERROR: ${data.error}`, 'bot');
            } else {
                addMessage(data.answer, 'bot', data.sources);
            }
        } catch (err) {
            addMessage(`CONNECTION_LOSS: ${err.message}`, 'bot');
        } finally {
            inputField.disabled = false;
            inputField.focus();
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    inputField.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});
