
$(document).on('keypress',function(e) {
  if(e.which == 13) {
    var current_input = $(".current input");

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
  }
});

