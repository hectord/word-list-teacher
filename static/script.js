

$(document).ready(function() {

  $.ajax({
    url: "/new_session",
    type: "POST"
  }).done(function(data) {
    var word = data.word;
    $("#current-input").text(word.input);
  });

  $("#current-output").keyup(function(e) {

    if($(this).attr('readonly'))
      return;

    if(e.which == 13) {
      var current_input = $(".current input");
      var output = current_input.val();

      current_input.attr("readonly", "");

      $.ajax({
        url: "/word",
        method: "POST",
        contentType: 'application/json',
        processData: false,
        data: JSON.stringify({"word": output})
      }).done(function() {
        if(current_input.val() === "die Haut") {
          var new_node = $("#right-word").clone();
        } else {
          var new_node = $("#wrong-word").clone();
        }

        new_node.attr("style", "");

        $(".current").before(new_node);

        current_input.val("");

        // update the size of the words
        var size = $(".words").css("height");
        $(".centering-box").css("top", "calc(50% - " + size + ")");
      });
    }
  });

});
