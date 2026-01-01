# Transport layer - builds all transport implementations
# Subdirectories: local/, network/, serial/

SUBDIRS = local network serial

all:
	@for dir in $(SUBDIRS); do \
		$(MAKE) -C $$dir || exit 1; \
	done

clean:
	@for dir in $(SUBDIRS); do \
		$(MAKE) -C $$dir clean; \
	done

.PHONY: all clean
