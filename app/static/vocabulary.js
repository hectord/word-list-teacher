// Word list filtering for the /vocabulary page:
// - click a section tile to filter the word list to that section
// - click the "N hard words" count to show only the hard words
// - type in the filter box to narrow by text
// The three filters combine.
$(function () {
  var $rows = $("#word-list .row[data-search]");
  var $count = $("#filter-count");
  var $filter = $("#word-filter");
  var $cards = $(".section-card");
  var $hard = $(".hard-filter");

  var activeSection = "";   // "" = whole vocabulary
  var activeHard = false;

  function matches(q, section, hard, $row) {
    if (section) {
      var rowSection = $row.data("section") || "";
      if (rowSection !== section) {
        return false;
      }
    }
    if (hard && $row.attr("data-hard") !== "1") {
      return false;
    }
    if (q) {
      return ($row.data("search") || "").indexOf(q) !== -1;
    }
    return true;
  }

  function apply() {
    var q = $filter.length ? $filter.val().toLowerCase().trim() : "";
    var visible = 0;

    $rows.each(function () {
      var show = matches(q, activeSection, activeHard, $(this));
      $(this).toggle(show);
      if (show) { visible++; }
    });

    if ($count.length) {
      $count.text(visible + " / " + $rows.length + " shown");
    }
  }

  function activate(name, $card) {
    activeSection = name;
    $cards.removeClass("active");
    $card.addClass("active");
  }

  function wholeVocabularyCard() {
    return $cards.filter(".all");
  }

  function openWordList() {
    // the word list may be collapsed for big vocabularies
    var $toggle = $(".word-list-toggle");
    if ($toggle.length) {
      $toggle.prop("open", true);
    }
  }

  $cards.on("click", ".section-filter", function (e) {
    e.preventDefault();

    var $card = $(this).closest(".section-card");
    var name = $card.data("section-name");

    if (name === "") {
      // "Whole vocabulary" tile -> show every word
      activate("", wholeVocabularyCard());
    } else if ($card.hasClass("active")) {
      // clicking the active section again -> back to whole vocabulary
      activate("", wholeVocabularyCard());
    } else {
      activate(name, $card);
    }

    openWordList();
    apply();
  });

  $hard.on("click", function () {
    activeHard = !activeHard;
    $(this).toggleClass("active", activeHard);
    openWordList();
    apply();
  });

  $filter.on("input", apply);
});