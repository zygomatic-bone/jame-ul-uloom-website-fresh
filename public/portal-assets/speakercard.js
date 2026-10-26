/* The new profile card on Bayanath.html: slow photograph slideshow, soft entrance, pointer light, and the latest videos
   (the newest few from data/bayanath-videos.json, the same file the video list uses, so they stay in step with the weekly update).
   Nothing here is needed to read the card: without JavaScript the photographs are a swipeable row and every link works. */
(function(){
    'use strict';
    var card = document.querySelector('[data-speakercard]');
    if(!card){ return; }
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var hasIO = 'IntersectionObserver' in window;

    /* ---------- entrance, and pausing the float while the card is off screen ---------- */
    var shown = false;
    function reveal(){
        if(shown){ return; }
        shown = true;
        card.classList.add('is-in');
    }
    card.classList.add('is-armed');
    if(hasIO){
        new IntersectionObserver(function(entries){
            var e = entries[entries.length - 1];
            card.classList.toggle('is-off', !e.isIntersecting);
            if(e.isIntersecting){ reveal(); }
            card.dispatchEvent(new CustomEvent('sc-visible', { detail: e.isIntersecting }));
        }, { threshold: 0.05 }).observe(card);
    } else {
        reveal();
    }
    window.setTimeout(reveal, 3000);   // safety net: the card is never left hidden

    /* ---------- pointer light (desktop only) ---------- */
    var panel = card.querySelector('.sc-panel');
    if(panel && !reduce && window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches){
        var raf = 0, px = 50, py = 30;
        panel.addEventListener('pointermove', function(e){
            var r = panel.getBoundingClientRect();
            px = ((e.clientX - r.left) / r.width) * 100;
            py = ((e.clientY - r.top) / r.height) * 100;
            if(!raf){
                raf = window.requestAnimationFrame(function(){
                    raf = 0;
                    panel.style.setProperty('--mx', px.toFixed(1) + '%');
                    panel.style.setProperty('--my', py.toFixed(1) + '%');
                });
            }
        });
        panel.addEventListener('pointerenter', function(){ panel.classList.add('is-lit'); });
        panel.addEventListener('pointerleave', function(){ panel.classList.remove('is-lit'); });
    }

    /* ---------- slideshow ---------- */
    var show = card.querySelector('.sc-show');
    var stage = show && show.querySelector('.sc-stage');
    var slides = stage ? Array.prototype.slice.call(stage.querySelectorAll('.sc-slide')) : [];
    var dots = show ? Array.prototype.slice.call(show.querySelectorAll('.sc-dot')) : [];
    if(show && slides.length > 1){
        var interval = (parseInt(card.getAttribute('data-interval'), 10) || 10) * 1000;
        var FADE = reduce ? 450 : 1700;
        var ctl = show.querySelector('.sc-ctl');
        var bar = show.querySelector('.sc-bar');
        var pp = show.querySelector('.sc-pp');
        var live = show.querySelector('.sc-live');
        var cur = 0, userPaused = reduce, hold = {}, held = false, timer = 0, startedAt = 0, remaining = interval, leaveTimer = 0;

        show.classList.add('is-js');
        stage.scrollLeft = 0;
        ctl.hidden = false; bar.hidden = false;
        show.style.setProperty('--sc-ms', (interval / 1000) + 's');
        if(reduce){ show.classList.add('is-still'); }

        var kb = function(slide){
            // a frame later, so the zoom starts from rest
            window.requestAnimationFrame(function(){ window.requestAnimationFrame(function(){ if(slide.classList.contains('is-active')){ slide.classList.add('is-kb'); } }); });
        };
        if(!reduce){ kb(slides[0]); }
        // pausing the slideshow also holds the slow zoom where it is, and playing lets it carry on
        var imgOf = function(slide){ return slide.querySelector('.sc-img'); };
        var freeze = function(slide){
            var i = imgOf(slide);
            if(!slide.classList.contains('is-kb')){ return; }
            var t = window.getComputedStyle(i).transform;
            i.style.transition = 'none'; i.style.transform = t;
        };
        var thaw = function(slide){ var i = imgOf(slide); i.style.transition = ''; i.style.transform = ''; };

        var anyHold = function(){ return hold.hover || hold.focus || hold.off || hold.hidden; };
        var syncHeld = function(){
            held = anyHold() || userPaused;
            show.classList.toggle('is-held', held);
        };
        var stop = function(){
            if(timer){ window.clearTimeout(timer); timer = 0; remaining -= (Date.now() - startedAt); if(remaining < 400){ remaining = 400; } }
        };
        var start = function(){
            if(timer || userPaused || anyHold()){ return; }
            startedAt = Date.now();
            timer = window.setTimeout(function(){ timer = 0; go(cur + 1, 1, true); }, remaining);
        };
        var refresh = function(){ syncHeld(); if(held){ stop(); } else { start(); } };

        var go = function(n, dir, auto){
            n = (n + slides.length) % slides.length;
            if(n === cur){ return; }
            var old = slides[cur], nu = slides[n];
            window.clearTimeout(leaveTimer);
            // any slide still leaving from an earlier change is finished at once
            slides.forEach(function(s){ if(s !== old && s !== nu){ s.classList.remove('is-active', 'is-leaving', 'is-kb'); thaw(s); } });
            old.classList.remove('is-active');
            old.classList.add('is-leaving');
            nu.classList.remove('is-leaving', 'is-kb');
            nu.classList.add('is-active');
            if(!reduce && !userPaused){ kb(nu); }
            leaveTimer = window.setTimeout(function(){ old.classList.remove('is-leaving', 'is-kb'); thaw(old); }, FADE);
            dots[cur].classList.remove('is-active'); dots[cur].removeAttribute('aria-current');
            dots[n].classList.add('is-active'); dots[n].setAttribute('aria-current', 'true');
            cur = n;
            if(!auto){ live.textContent = 'Photograph ' + (n + 1) + ' of ' + slides.length; }
            stop(); timer = 0; remaining = interval;
            refresh();
        };

        show.querySelector('.sc-prev').addEventListener('click', function(){ go(cur - 1, -1, false); });
        show.querySelector('.sc-next').addEventListener('click', function(){ go(cur + 1, 1, false); });
        dots.forEach(function(d, i){ d.addEventListener('click', function(){ go(i, i > cur ? 1 : -1, false); }); });

        var setPaused = function(p){
            userPaused = p;
            pp.classList.toggle('is-paused', p);
            pp.setAttribute('aria-pressed', p ? 'true' : 'false');
            pp.setAttribute('aria-label', p ? 'Play the slideshow' : 'Pause the slideshow');
            if(!p){ show.classList.remove('is-still'); }
            if(p){ stop(); if(!reduce){ freeze(slides[cur]); } }
            else if(!reduce){
                if(slides[cur].classList.contains('is-kb')){ thaw(slides[cur]); } else { kb(slides[cur]); }
            }
            refresh();
        };
        pp.addEventListener('click', function(){ setPaused(!userPaused); });
        if(reduce){ setPaused(true); }

        // keyboard
        show.addEventListener('keydown', function(e){
            if(e.key === 'ArrowLeft'){ e.preventDefault(); go(cur - 1, -1, false); }
            else if(e.key === 'ArrowRight'){ e.preventDefault(); go(cur + 1, 1, false); }
        });

        // pause while the pointer rests on it or focus is inside; resume afterwards
        show.addEventListener('mouseenter', function(){ hold.hover = true; refresh(); });
        show.addEventListener('mouseleave', function(){ hold.hover = false; refresh(); });
        show.addEventListener('focusin', function(){ hold.focus = true; refresh(); });
        show.addEventListener('focusout', function(){ hold.focus = false; refresh(); });
        document.addEventListener('visibilitychange', function(){ hold.hidden = document.hidden; refresh(); });
        card.addEventListener('sc-visible', function(e){ hold.off = !e.detail; refresh(); });

        // swipe (and mouse drag): a horizontal flick changes the photograph, a vertical one still scrolls the page
        var sx = 0, sy = 0, sid = null;
        stage.addEventListener('pointerdown', function(e){
            if(e.pointerType === 'mouse' && e.button !== 0){ return; }
            sx = e.clientX; sy = e.clientY; sid = e.pointerId; stage.classList.add('is-drag');
        });
        var end = function(e){
            if(sid === null || e.pointerId !== sid){ return; }
            var dx = e.clientX - sx, dy = e.clientY - sy;
            sid = null; stage.classList.remove('is-drag');
            if(e.type === 'pointerup' && Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.4){ go(dx < 0 ? cur + 1 : cur - 1, dx < 0 ? 1 : -1, false); }
        };
        stage.addEventListener('pointerup', end);
        stage.addEventListener('pointercancel', end);
        stage.addEventListener('dragstart', function(e){ e.preventDefault(); });

        hold.hidden = document.hidden;
        hold.off = hasIO;   // until the observer reports that the card is on screen
        refresh();
    }

    /* ---------- latest videos ---------- */
    var latest = card.querySelector('[data-sc-latest]');
    var board = document.querySelector('[data-bayanath]');
    if(latest && board){
        var list = latest.querySelector('.sc-vids');
        var count = parseInt(latest.getAttribute('data-sc-count'), 10) || 3;
        var ID = /^[A-Za-z0-9_-]{11}$/;
        var THUMB = /^https:\/\/(?:i\d?\.ytimg\.com|img\.youtube\.com)\//;
        var el = function(tag, cls, text){
            var n = document.createElement(tag);
            if(cls){ n.className = cls; }
            if(text){ n.textContent = text; }
            return n;
        };
        var when = function(iso){
            if(!iso){ return ''; }
            var d = new Date(iso);
            return isNaN(d) ? '' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
        };
        var item = function(v){
            var li = el('li');
            var a = el('a', 'sc-vid');
            a.href = 'https://www.youtube.com/watch?v=' + v.id;
            a.target = '_blank'; a.rel = 'noopener noreferrer';
            a.setAttribute('aria-label', 'Watch on YouTube: ' + v.title + ' (opens in a new tab)');
            var th = el('span', 'sc-vthumb');
            var img = new Image();
            img.alt = ''; img.loading = 'lazy'; img.decoding = 'async'; img.width = 480; img.height = 360;
            img.referrerPolicy = 'no-referrer';
            var canonical = 'https://i.ytimg.com/vi/' + v.id + '/hqdefault.jpg';
            var approved = (typeof v.thumbnail === 'string' && THUMB.test(v.thumbnail) && v.thumbnail.indexOf('/' + v.id + '/') !== -1) ? v.thumbnail : canonical;
            img.src = approved;
            img.addEventListener('error', function(){
                if(img.src !== canonical){ img.src = canonical; } else { img.remove(); }
            });
            th.appendChild(img);
            var tx = el('span', 'sc-vtext');
            tx.appendChild(el('span', 'sc-vtitle', v.title));
            var d = when(v.published);
            if(d){ tx.appendChild(el('span', 'sc-vdate', d)); }
            a.appendChild(th); a.appendChild(tx); li.appendChild(a);
            return li;
        };
        var loaded = false;
        var load = function(){
            if(loaded){ return; }
            loaded = true;
            fetch(board.getAttribute('data-src') || 'data/bayanath-videos.json', { cache: 'no-cache' })
                .then(function(r){ if(!r.ok){ throw new Error('status ' + r.status); } return r.json(); })
                .then(function(data){
                    var vids = (data && data.videos || []).filter(function(v){ return v && ID.test(v.id || '') && typeof v.title === 'string' && v.title; });
                    vids.sort(function(a, b){ return (Date.parse(b.published) || 0) - (Date.parse(a.published) || 0); });
                    vids.slice(0, count).forEach(function(v){ list.appendChild(item(v)); });
                    if(list.children.length){ latest.hidden = false; }
                })
                .catch(function(){ /* the section simply stays hidden */ });
        };
        if(hasIO){
            var lo = new IntersectionObserver(function(es){
                if(es[0].isIntersecting){ lo.disconnect(); load(); }
            }, { rootMargin: '400px 0px' });
            lo.observe(card);
        } else {
            load();
        }
    }
})();
