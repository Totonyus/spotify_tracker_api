const socket = new WebSocket("ws/refresh_status");
let scan_running = false;

socket.addEventListener("message", (event) => {
    const dom_element = document.getElementById('refresh_status');
    const status = JSON.parse(event.data);
    scan_running = status.scan_running

    if (scan_running) {
        dom_element.innerHTML = `<span class="category_item"><span>Running scan</span> ➤ <span>${status.current_artist + status.current_show} on ${status.total_artists + status.total_shows}</span></span>`;
    }else{
        dom_element.innerHTML = `<span class="category_item"><span>Scan complete</span> ➤ <span><a class="api_link_reference" href="#">Reload page</a></span></span>`;
        location.reload();
    }
});

socket.addEventListener("close", (event) => {
    if (!scan_running){
        return
    }

    const dom_element = document.getElementById('refresh_status');

    dom_element.innerHTML = `<span class="category_item error"><span>An error occurred during scan</span> ➤ <span><a class="api_link_reference" href="/refresh">/refresh</a></span></span>`;
});

socket.addEventListener("error", (event) => {
    if (!scan_running){
        return
    }

    const dom_element = document.getElementById('refresh_status');

    dom_element.innerHTML = `<span class="category_item error"><span>An error occurred during scan</span> ➤ <span><a class="api_link_reference" href="/refresh">/refresh</a></span></span>`;
});