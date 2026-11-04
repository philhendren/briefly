Feature: Choosing news sources
  As a household using Home Assistant
  I want to pick which news sources each section shows
  So that my news desk carries the outlets I trust, with no publisher that blocks fetching

  Background:
    Given the standard news feeds are available

  Scenario: Sources are offered as a list of fetch-friendly presets
    When I start setting up a news desk called "Kiosk news"
    Then the section form offers the source "BBC News · UK"
    And the section form offers the source "The Guardian · Politics"
    And the section form offers no "Sky News" source
    And the sources are shown as a list, not a drop-down

  Scenario: A section shows stories from the chosen sources
    When I set up a news desk called "Kiosk news" with a section "UK" using "bbc_uk, guardian_uk"
    Then "sensor.kiosk_news_uk" lists 3 stories
    And every story in "sensor.kiosk_news_uk" comes from "BBC News" or "The Guardian"

  Scenario: The same story from two outlets is shown once
    When I set up a news desk called "Kiosk news" with a section "UK" using "bbc_uk, guardian_uk"
    Then the lead story in "sensor.kiosk_news_uk" is "Council approves 250 new homes on town edge"
    And the lead story in "sensor.kiosk_news_uk" is also reported by "The Guardian"

  Scenario: A custom feed that is not RSS is refused
    When I start setting up a news desk called "Kiosk news"
    And I add a section "Local" with the custom feed "https://example.org/news.xml" that serves a web page
    Then the form shows the error "invalid_feed" for "custom_feeds"
