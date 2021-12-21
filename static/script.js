

$(document).ready(function() {

  $.ajax({
    url: "/new_session",
    type: "POST"
  }).done(function(data) {
    $("#current-input").text(data.word);
  });

  $("#current-output").keyup(function(e) {

    if($(this).attr('readonly'))
      return;

    if(e.which == 13) {
      var current_input = $("#current-input");
      var current_output = $("#current-output");
      var output = current_output.val();

      current_output.attr("readonly", true);

      $.ajax({
        url: "/word",
        method: "POST",
        contentType: 'application/json',
        processData: false,
        data: JSON.stringify({"word": output})
      }).done(function(result) {

        if(result.success) {
          var new_node = $("#right-word").clone();
        } else {
          var new_node = $("#wrong-word").clone();
        }

        new_node.attr("style", "");
        new_node.find(".input .field").text(result.word_input.word);
        new_node.find(".output .field").text(result.word_output.word);
        new_node.find(".result .field").text(result.hint);

        $(".current").before(new_node);

        if(result.next_word) {
          current_input.text(result.next_word.word)
          current_output.val("");
          current_output.attr("readonly", false);
        } else {
          $("#current-word").hide();
        }

        // update the size of the words
        var size = $(".words").css("height");
        $(".centering-box").css("top", "calc(50% - " + size + ")");
      });
    }
  });

});
