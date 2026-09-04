/**
 * SWIPIES Traffic Attribution & Analytics Client Tracker (Track 3)
 * Size: < 3.5 KB gzip, Zero dependencies, Vanilla JS.
 * Features:
 * - Robust session_id generation and persistence
 * - First-touch UTM cookie (30 days) and session storage
 * - Active engagement time tracking via Document Visibility API (pauses in background tabs)
 * - Reliable delivery using Fetch with keepalive and Navigator.sendBeacon
 * - Graceful fallback in incognito or blocked storage environments
 */
(function (window, document) {
    'use strict';

    if (window.__SWIPIES_TRACKER_LOADED__) return;
    window.__SWIPIES_TRACKER_LOADED__ = true;

    var ENDPOINT = '/api/v1/track/event';
    var COOKIE_NAME = '_swp_utm';
    var SESSION_KEY = '_swp_session_id';
    var COOKIE_EXPIRY_DAYS = 30;
    var HEARTBEAT_INTERVAL_MS = 30000;

    // Memory fallbacks for incognito/cookies disabled
    var memStore = {};

    function safeGetItem(key) {
        try {
            return window.sessionStorage ? window.sessionStorage.getItem(key) : memStore[key];
        } catch (e) {
            return memStore[key] || null;
        }
    }

    function safeSetItem(key, val) {
        try {
            if (window.sessionStorage) window.sessionStorage.setItem(key, val);
            memStore[key] = val;
        } catch (e) {
            memStore[key] = val;
        }
    }

    function getCookie(name) {
        try {
            var match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
            return match ? decodeURIComponent(match[3]) : null;
        } catch (e) {
            return null;
        }
    }

    function setCookie(name, val, days) {
        try {
            var expires = '';
            if (days) {
                var d = new Date();
                d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
                expires = '; expires=' + d.toUTCString();
            }
            document.cookie = name + '=' + encodeURIComponent(val) + expires + '; path=/; SameSite=Lax';
        } catch (e) {
            // Ignored if cookies blocked
        }
    }

    function generateSessionId() {
        var rand = Math.random().toString(36).substring(2, 14);
        var time = Date.now().toString(36);
        return 'swp_' + time + '_' + rand;
    }

    var sessionId = safeGetItem(SESSION_KEY);
    if (!sessionId) {
        sessionId = generateSessionId();
        safeSetItem(SESSION_KEY, sessionId);
    }

    function parseUtmParams() {
        var params = {};
        var search = window.location.search;
        if (!search) return params;

        var pairs = search.substring(1).split('&');
        for (var i = 0; i < pairs.length; i++) {
            var pair = pairs[i].split('=');
            if (pair.length === 2) {
                var key = decodeURIComponent(pair[0]).toLowerCase();
                var val = decodeURIComponent(pair[1]);
                if (key.indexOf('utm_') === 0 || key === 'fbclid') {
                    params[key] = val.substring(0, 128);
                }
            }
        }
        return params;
    }

    var currentUtm = parseUtmParams();
    var hasNewUtm = Object.keys(currentUtm).length > 0;

    // First-touch attribution storage (30 days cookie)
    var storedUtmJson = getCookie(COOKIE_NAME);
    var firstTouchUtm = {};
    if (storedUtmJson) {
        try {
            firstTouchUtm = JSON.parse(storedUtmJson);
        } catch (e) {
            firstTouchUtm = {};
        }
    }

    if (hasNewUtm) {
        safeSetItem('_swp_active_utm', JSON.stringify(currentUtm));
        if (!storedUtmJson || Object.keys(firstTouchUtm).length === 0) {
            setCookie(COOKIE_NAME, JSON.stringify(currentUtm), COOKIE_EXPIRY_DAYS);
            firstTouchUtm = currentUtm;
        }
    } else {
        var sessionUtm = safeGetItem('_swp_active_utm');
        if (sessionUtm) {
            try {
                currentUtm = JSON.parse(sessionUtm);
            } catch (e) {
                currentUtm = {};
            }
        } else if (firstTouchUtm && Object.keys(firstTouchUtm).length > 0) {
            currentUtm = firstTouchUtm;
        }
    }

    // Active Time Tracking (Pausing in Background Tabs)
    var accumulatedActiveSec = 0;
    var lastActiveTimestamp = Date.now();
    var isVisible = (document.visibilityState === 'visible');

    function updateActiveTime() {
        var now = Date.now();
        if (isVisible) {
            var delta = Math.floor((now - lastActiveTimestamp) / 1000);
            if (delta > 0) {
                accumulatedActiveSec += delta;
                lastActiveTimestamp = now;
            }
        } else {
            lastActiveTimestamp = now;
        }
    }

    function getActiveTimeSeconds() {
        updateActiveTime();
        return Math.min(accumulatedActiveSec, 86400);
    }

    function onVisibilityChange() {
        if (document.visibilityState === 'visible') {
            isVisible = true;
            lastActiveTimestamp = Date.now();
        } else {
            updateActiveTime();
            isVisible = false;
            sendEvent('heartbeat');
        }
    }

    document.addEventListener('visibilitychange', onVisibilityChange);

    function buildPayload(eventType) {
        return {
            session_id: sessionId,
            page_path: window.location.pathname.substring(0, 255) || '/',
            time_on_page_sec: getActiveTimeSeconds(),
            utm_source: currentUtm.utm_source || null,
            utm_medium: currentUtm.utm_medium || null,
            utm_campaign: currentUtm.utm_campaign || null,
            utm_content: currentUtm.utm_content || null,
            utm_term: currentUtm.utm_term || null,
            referrer: (document.referrer || '').substring(0, 512) || null,
            event_type: eventType || 'pageview'
        };
    }

    function sendEvent(eventType, isSync) {
        var payload = buildPayload(eventType);
        var bodyStr = JSON.stringify(payload);

        if (isSync && navigator.sendBeacon) {
            try {
                var blob = new Blob([bodyStr], { type: 'application/json' });
                navigator.sendBeacon(ENDPOINT, blob);
                return;
            } catch (e) {
                // Fall through to fetch
            }
        }

        if (window.fetch) {
            try {
                window.fetch(ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: bodyStr,
                    keepalive: true
                }).catch(function () {});
            } catch (e) {}
        }
    }

    // Initial pageview
    sendEvent('pageview');

    // Periodic heartbeat for engaged time
    var heartbeatTimer = setInterval(function () {
        if (document.visibilityState === 'visible') {
            sendEvent('heartbeat');
        }
    }, HEARTBEAT_INTERVAL_MS);

    // Unload / Leave Beacon
    function onUnload() {
        clearInterval(heartbeatTimer);
        sendEvent('leave', true);
    }

    window.addEventListener('pagehide', onUnload);
    window.addEventListener('beforeunload', onUnload);

    // Global Tracker API
    window.__SWIPIES_TRACKER__ = {
        getSessionId: function () { return sessionId; },
        getUtm: function () { return currentUtm; },
        getActiveSeconds: getActiveTimeSeconds,
        trackConversion: function (details) {
            var payload = buildPayload('conversion');
            if (details && typeof details === 'object') {
                payload.conversion_details = details;
            }
            sendEvent('conversion');
        }
    };
})(window, document);
