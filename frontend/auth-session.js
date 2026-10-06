'use strict';
// Preserve same-origin API responses. Renewal is always this fixed local page.
(()=>{const originalFetch=window.fetch.bind(window);window.fetch=async(...args)=>{const ticket=window.FireAISession?.currentGeneration();const response=await originalFetch(...args);if((ticket===undefined||ticket===window.FireAISession?.currentGeneration())&&response.headers.get('X-FireAI-Password-Renewal')==='required'&&window.location.pathname!=='/ui/password.html')window.location.replace('/ui/password.html');return response;};})();
