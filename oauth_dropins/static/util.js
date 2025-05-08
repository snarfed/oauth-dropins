/* Add http:// to URL fields on blur or when enter is pressed.
 * From https://aaronparecki.com/2018/06/03/4/url-form-field
 * Thanks Aaron!
 *
 * Warning: this script must be loaded synchronously, ie *not* with <script
 * async>. It adds an event listener on DOMContentLoaded, which some browsers
 * (eg Chrome) may fire before async scripts are loaded.
 */
var openedId;

document.addEventListener('DOMContentLoaded', function() {
  function addDefaultScheme(target) {
    val = target.value.trim()
    if(val.match(/^(?!https?:)[^@]+\.[^@]+$/)) {
      scheme = target.attributes.scheme;
      target.value = (scheme ? scheme.value : "http") + "://" + val;
    }
  }
  var elements = document.querySelectorAll("input[type=url]");
  Array.prototype.forEach.call(elements, function(el, i){
    el.addEventListener("blur", function(e){
      addDefaultScheme(e.target);
    });
    el.addEventListener("keydown", function(e){
      if(e.keyCode == 13) {
        addDefaultScheme(e.target);
      }
    });
  });
});

/* Hide flashed messages in Flask. CSS transition in util.css fades them out slowly.
 */
window.onload = function () {
  for (const p of document.getElementsByClassName('message')) {
    window.setTimeout(function() {
      p.style.opacity = 0;  // uses delayed transition
    }, 5 /* ms; needed for transition after setting display to non-none */);

    window.setTimeout(function() {
      p.style.display = 'none';
    }, (20 + 5) * 1000 /* ms; match transition duration + delay */);
  }
}

function toggleInput(button_id) {
  var button = document.getElementById(button_id);
  var input = document.getElementById(button_id + "-input");
  var submit = document.getElementById(button_id + "-submit");
  if (input) {
    if (openedId && openedId != button_id) {
      document.getElementById(openedId).classList.remove("slide-up");

      document.getElementById(openedId + "-submit").classList.remove("visible");
      document.getElementById(openedId + "-input").classList.remove("visible");

      openedId = null;
    }

    if(input.classList.contains("visible")){
      submit.classList.remove("visible");
      input.classList.remove("visible");

      button.classList.remove("slide-up");

      openedId = null;
    } else {
      openedId = button_id;

      button.classList.add("slide-up");

      submit.classList.add("visible");
      input.classList.add("visible");
      input.focus();
    }
  } else {
    submit.click();
  }
}
