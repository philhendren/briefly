Feature: Spoken headlines through Alexa
  As a household with Amazon Echo devices
  I want Briefly to read the top headlines aloud
  Using Alexa Media Player, which is a separate custom integration from HACS

  Background:
    Given the standard news feeds are available

  Scenario: Headlines are read on the chosen Echo
    Given Alexa Media Player is installed
    And a news desk with spoken headlines on "media_player.kitchen_echo"
    When I ask Briefly to speak 2 headlines from "UK"
    Then Alexa is asked to say "Here are the top 2 headlines from UK news." on "media_player.kitchen_echo"
    And Alexa is asked to say "From BBC News: Council approves 250 new homes on town edge."

  Scenario: Setup explains that Alexa Media Player is needed
    Given Alexa Media Player is not installed
    When I try to turn on spoken headlines while setting up a news desk
    Then the form shows the error "alexa_media_missing"
    And the form links to "https://github.com/alandtse/alexa_media_player"

  Scenario: Spoken headlines are off unless chosen
    Given Alexa Media Player is installed
    And a news desk without spoken headlines
    When I try to ask Briefly to speak headlines
    Then I am told spoken headlines are switched off
