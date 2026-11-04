Feature: Optional Ollama summaries
  As a household with a local Ollama server
  I want each new story summarised once by a model I choose
  So that the news screen is easy to read without inventing facts

  Background:
    Given the standard news feeds are available
    And an Ollama server with the models "llama3.2:3b, qwen3:14b"

  Scenario: The model is chosen from the models Ollama has installed
    When I set up summaries with Ollama at "http://ollama.local:11434"
    Then the model drop-down offers "llama3.2:3b, qwen3:14b"

  Scenario: Ollama cannot be reached during setup
    Given Ollama is unreachable
    When I set up summaries with Ollama at "http://ollama.local:11434"
    Then the form shows the error "cannot_connect"

  Scenario: A faithful summary is shown
    Given a news desk with summaries written by "qwen3:14b"
    Then the story "Council approves 250 new homes" has summary status "done"
    And the summary of "Council approves 250 new homes" mentions "250 new homes"
    And Ollama was asked to use the model "qwen3:14b" with structured output

  Scenario: A summary with an invented number is rejected
    Given Ollama invents the number 999 in every summary
    And a news desk with summaries written by "qwen3:14b"
    Then the story "Council approves 250 new homes" has summary status "feed_only"
    And the story "Council approves 250 new homes" shows its feed description

  Scenario: Ollama going offline is retried three times, then left alone
    Given Ollama is unreachable
    And a news desk with summaries written by "qwen3:14b"
    Then the story "Council approves 250 new homes" has summary status "pending"
    When the news desk refreshes 2 more times
    Then the story "Council approves 250 new homes" has summary status "feed_only"
    And Ollama receives no more requests when the desk refreshes again

  Scenario: A publisher that refuses automated fetching is respected
    Given "www.bbc.co.uk" refuses article requests with HTTP 403
    And a news desk with summaries written by "qwen3:14b"
    Then the story "Council approves 250 new homes" has summary status "feed_only"
    And the story "Weekend rail disruption" has summary status "feed_only"
    And no request was made for "https://www.bbc.co.uk/news/articles/rail1"

  Scenario Outline: Summary length controls the prompt
    Given a news desk with "<length>" summaries written by "qwen3:14b"
    Then Ollama was asked for "<words>"

    Examples:
      | length   | words                  |
      | headline | one sentence           |
      | short    | 90 to 140 words        |
      | medium   | 150 to 220 words       |
