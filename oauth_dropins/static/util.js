/* Add http:// to URL fields on blur or when enter is pressed.
 * From https://aaronparecki.com/2018/06/03/4/url-form-field
 * Thanks Aaron!
 */
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
