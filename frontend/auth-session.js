'use strict';
// Preserve same-origin API responses. Renewal is always this fixed local page.
(()=>{const originalFetch=window.fetch.bind(window);window.fetch=async(...args)=>{const response=await originalFetch(...args);if(response.headers.get('X-FireAI-Password-Renewal')==='required'&&window.location.pathname!=='/ui/password.html')window.location.replace('/ui/password.html');return response;};})();
